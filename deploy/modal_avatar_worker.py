"""Independent Modal LongCat-Avatar 1.5 pilot. No Studio IA resources touched.

The old LTX app and volume are deliberately NOT used. Model preparation is a
separate CPU function; GPU inference is never attempted with missing weights.
This is experimental until an actual avatar MP4 is rendered and reviewed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import modal

from deploy.modal_avatar_models import ROOT, AVATAR, models, inspection
from backend.app.avatar import diagnostic_inputs, finish_avatar, plan_audio, select_output

APP_NAME = os.environ.get('PVS_MODAL_AVATAR_APP', 'pvs-longcat-avatar')
GPU_NAME = "A100-80GB"
app = modal.App(APP_NAME)

# Upstream instructions: PyTorch 2.6 cu124 and flash-attn 2.7.4.post1.
# The devel image is required to build flash-attn; one build can take minutes.
render_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04", add_python="3.10"
    )
    .apt_install(
        "git", "ffmpeg", "build-essential", "libgl1", "libglib2.0-0",
        "libsndfile1", "libsm6", "libxext6",
    )
    .run_commands(
        "pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124",
        "pip install ninja psutil packaging setuptools wheel",
        "git clone https://github.com/meituan-longcat/LongCat-Video.git /opt/LongCat-Video && cd /opt/LongCat-Video && git checkout 6b3f4b8582a8bc3f20f795735f5383716c4ba794",
        "MAX_JOBS=2 pip install flash_attn==2.7.4.post1 --no-build-isolation",
        # libsndfile1 is installed by apt; tritonserverclient is unpublished and unused by inference.
        "sed -e '/^libsndfile1==/d' -e '/^tritonserverclient==/d' /opt/LongCat-Video/requirements_avatar.txt > /opt/LongCat-Video/requirements_avatar_python.txt",
        "pip install -r /opt/LongCat-Video/requirements.txt -r /opt/LongCat-Video/requirements_avatar_python.txt",
        "cd /opt/LongCat-Video && python -c 'import ctypes; ctypes.CDLL(\"libsndfile.so.1\"); from longcat_video.pipeline_longcat_video_avatar import LongCatVideoAvatarPipeline; from audio_separator.separator import Separator'",
    )
    .add_local_python_source('backend')
)


@app.function(image=render_image, cpu=1, memory=512, timeout=60, max_containers=1, scaledown_window=2)
def check_runtime():
    return {'backend_import': True, 'one_segment': plan_audio(3.68),
            'two_segments': plan_audio(6.92, max_segments=2)}


@app.function(
    image=render_image,
    gpu=GPU_NAME,
    cpu=8,
    memory=65536,
    timeout=1800,
    min_containers=0,
    max_containers=1,
    scaledown_window=2,
    volumes={
        str(ROOT): models.with_mount_options(read_only=True)
        if hasattr(models, "with_mount_options") else models
    },
)
def render_avatar(image_b64: str, audio_b64: str, prompt: str, num_segments: int = 1) -> dict:
    """Audio-led avatar with official context-frame continuation, then source-audio mux."""
    if not inspection()["ready"]:
        raise RuntimeError("LongCat models absent/incomplete: run --mode prepare first")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pvs-avatar-") as temp:
        folder = Path(temp)
        img_path = folder / "reference.png"
        audio_path = folder / "french_voice.wav"
        img_path.write_bytes(base64.b64decode(image_b64, validate=True))
        audio_path.write_bytes(base64.b64decode(audio_b64, validate=True))
        if not img_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Expected PNG reference")
        if not audio_path.read_bytes().startswith(b"RIFF"):
            raise ValueError("Expected PCM WAV speech")
        with wave.open(str(audio_path), 'rb') as wav:
            if wav.getsampwidth() != 2 or wav.getcomptype() != 'NONE':
                raise ValueError('Expected PCM16 WAV speech')
            source_duration = wav.getnframes() / wav.getframerate()
        plan = plan_audio(source_duration, max_segments=num_segments)
        num_segments = plan['num_segments']
        payload = {
            "prompt": prompt,
            "cond_image": str(img_path),
            "cond_audio": {"person1": str(audio_path)},
        }
        input_path = folder / "avatar_input.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        output = folder / "raw"
        output.mkdir()
        cmd = [
            "torchrun", "--standalone", "--nnodes=1", "--nproc_per_node=1",
            "run_demo_avatar_single_audio_to_video.py",
            "--context_parallel_size=1",
            f"--checkpoint_dir={AVATAR}",
            "--stage_1=ai2v",
            f"--input_json={input_path}",
            f"--output_dir={output}",
            "--model_type=avatar-v1.5",
            "--resolution=480p",
            "--use_distill", "--use_int8",
            f'--num_segments={num_segments}',
            '--ref_img_index=10', '--mask_frame_range=3',
        ]
        print(f'Running official LongCat Avatar v1.5, INT8, 480p, {num_segments} segment(s)', flush=True)
        samples_path = folder / "gpu.csv"
        with samples_path.open("w") as samples:
            monitor = subprocess.Popen(
                ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits", "-l", "1"],
                stdout=samples, stderr=subprocess.DEVNULL,
            )
            try:
                completed = subprocess.run(
                    cmd, cwd="/opt/LongCat-Video", text=True,
                    stderr=subprocess.STDOUT, timeout=1500,
                    env={**os.environ, "OMP_NUM_THREADS": "4", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
                )
            finally:
                monitor.terminate()
                monitor.wait(timeout=10)
        if completed.returncode:
            raise RuntimeError(f"LongCat failed with exit {completed.returncode}; see inference logs above")
        raw = select_output(output, num_segments)
        final = folder / "avatar_vertical.mp4"
        # Upstream uses aspect-ratio buckets; crop centrally to true 9:16
        # without stretching faces. Preserve speech and verify video/audio streams.
        finish_avatar(raw, audio_path, final, plan)
        meta = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height",
             "-show_entries", "format=duration,size",
             "-of", "json", str(final)], text=True,
        )
        detail = json.loads(meta)
        tracks = {s["codec_type"] for s in detail.get("streams", [])}
        if not {"video", "audio"}.issubset(tracks):
            raise RuntimeError("LongCat MP4 missing video or French audio track")
        if abs(float(detail['format']['duration']) - plan['output_frames'] / 25) > .08:
            raise RuntimeError('LongCat: durée finale incompatible avec la voix source')
        wall = round(time.perf_counter() - started, 2)
        samples = [tuple(float(v.strip()) for v in line.split(",")) for line in samples_path.read_text().splitlines()]
        import resource

        return {
            "video_b64": base64.b64encode(final.read_bytes()).decode("ascii"),
            "metadata": {
                "engine": "longcat-video-avatar-1.5",
                "gpu": GPU_NAME,
                "gpu_wall_seconds": wall,
                "gpu_peak_memory_mib": max((s[0] for s in samples), default=0),
                "gpu_mean_utilization_percent": round(sum(s[1] for s in samples) / max(1, len(samples)), 2),
                "child_peak_ram_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                "compute_cost_estimate_usd": round(wall * (0.000694 + 8 * 0.0000131 + 64 * 0.00000222), 4),
                "cost_basis": "GPU plus reserved CPU/RAM; excludes cold start and RAM bursts",
                "duration_seconds": float(detail["format"]["duration"]),
                "bytes": final.stat().st_size,
                "streams": detail["streams"],
                "status": "real_generated_avatar_not_quality_reviewed",
                'source_audio_sha256': hashlib.sha256(audio_path.read_bytes()).hexdigest(),
                'source_audio_duration_s': source_duration,
                'continuation': plan,
                'audio_policy': 'source_wav_reused_no_tts_no_time_stretch',
            },
        }


@app.local_entrypoint()
def main(
    mode: str = "render",
    image_png: str = "benchmark_assets/character_reference.png",
    audio_wav: str = "artifacts/voice_fr.wav",
    out: str = "artifacts/longcat_avatar_fr.mp4",
    num_segments: int = 1,
    voice_report: str = '',
    receipt: str = '',
    prompt: str = (
        "Photorealistic presenter, subtle expressions, looking at camera, speaking "
        "French naturally in a modern dark premium tech studio, soft cinematic lighting"
    ),
):
    if mode == 'doctor':
        print(json.dumps(check_runtime.remote()))
        return
    if mode != "render":
        raise SystemExit("Use deploy/modal_avatar_models.py for prepare/doctor; this app renders only")
    if num_segments == 2 and not voice_report:
        raise ValueError('Continuation diagnostique: rapport de voix validée requis')
    record = None
    if voice_report:
        if not receipt:
            raise ValueError('Diagnostic: fichier receipt requis pour conserver la tentative unique')
        photo, voice, plan = diagnostic_inputs(image_png, audio_wav, voice_report, num_segments)
        num_segments = plan['num_segments']
        check_runtime.remote()
        record = Path(receipt)
        record.parent.mkdir(parents=True, exist_ok=True)
        with record.open('x', encoding='utf-8') as stream:
            json.dump({'status': 'submitted_once', 'plan': plan, 'app': APP_NAME}, stream)
    else:
        photo = Path(image_png).read_bytes()
        voice = Path(audio_wav).read_bytes()
        with wave.open(str(audio_wav), 'rb') as wav:
            plan_audio(wav.getnframes() / wav.getframerate(), num_segments)
    call = render_avatar.spawn(
        base64.b64encode(photo).decode("ascii"),
        base64.b64encode(voice).decode("ascii"),
        prompt,
        num_segments,
    )
    if record:
        record.write_text(json.dumps({'status': 'running', 'call_id': call.object_id, 'plan': plan, 'app': APP_NAME}),
                          encoding='utf-8')
    completed = False
    try:
        result = call.get()
        completed = True
    finally:
        if not completed:
            call.cancel(terminate_containers=True)
            if record:
                record.write_text(json.dumps({'status': 'failed_or_cancelled', 'call_id': call.object_id,
                                              'plan': plan, 'app': APP_NAME}), encoding='utf-8')
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(result["video_b64"]))
    meta = path.with_suffix(".json")
    meta.write_text(json.dumps(result["metadata"], ensure_ascii=False, indent=2), encoding="utf-8")
    if record:
        record.write_text(json.dumps({'status': 'completed', 'call_id': call.object_id, 'plan': plan,
                                      'app': APP_NAME, 'output': str(path)}), encoding='utf-8')
    print(f"Avatar saved: {path} ({path.stat().st_size} bytes); metadata: {meta}")
