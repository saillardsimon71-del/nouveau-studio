"""Independent Modal LongCat-Avatar 1.5 pilot. No Studio IA resources touched.

The old LTX app and volume are deliberately NOT used. Model preparation is a
separate CPU function; GPU inference is never attempted with missing weights.
This is experimental until an actual avatar MP4 is rendered and reviewed.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import modal

APP_NAME = "pvs-longcat-avatar"
VOLUME_NAME = "pvs-longcat-models"
ROOT = Path("/models")
BASE = ROOT / "LongCat-Video"
AVATAR = ROOT / "LongCat-Video-Avatar-1.5"
GPU_NAME = "A100-80GB"

app = modal.App(APP_NAME)
models = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# CPU only: model downloads are persisted once, never baked into a GPU image.
download_image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install("huggingface_hub>=0.26,<2", "hf_xet")
)

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
        "git clone --depth 1 https://github.com/meituan-longcat/LongCat-Video.git /opt/LongCat-Video",
        "MAX_JOBS=2 pip install flash_attn==2.7.4.post1 --no-build-isolation",
        "pip install -r /opt/LongCat-Video/requirements.txt -r /opt/LongCat-Video/requirements_avatar.txt",
    )
)

NEEDED = {
    "base_tokenizer": BASE / "tokenizer",
    "base_encoder": BASE / "text_encoder",
    "base_vae": BASE / "vae",
    "avatar_int8": AVATAR / "base_model_int8",
    "avatar_lora": AVATAR / "lora",
    "avatar_scheduler": AVATAR / "scheduler",
    "avatar_whisper": AVATAR / "whisper-large-v3",
    "avatar_vocal_separator": AVATAR / "vocal_separator",
}


def inspection() -> dict:
    """Read-only diagnostic; a folder must contain at least one real file."""
    sections = {}
    for name, folder in NEEDED.items():
        files = [p for p in folder.rglob("*") if p.is_file()] if folder.is_dir() else []
        sections[name] = {
            "present": bool(files),
            "file_count": len(files),
            "bytes": sum(p.stat().st_size for p in files),
        }
    return {
        "app": APP_NAME,
        "volume": VOLUME_NAME,
        "sections": sections,
        "ready": all(section["present"] for section in sections.values()),
    }


@app.function(
    image=download_image,
    cpu=4,
    memory=16384,
    timeout=7200,
    volumes={str(ROOT): models},
)
def prepare_models() -> dict:
    """Download only the model components used by v1.5 INT8 into a NEW volume."""
    from huggingface_hub import snapshot_download

    os.environ.setdefault("HF_HOME", str(ROOT / ".hf_cache"))
    for repo, target, patterns in (
        (
            "meituan-longcat/LongCat-Video", BASE,
            ["tokenizer/**", "text_encoder/**", "vae/**"],
        ),
        (
            "meituan-longcat/LongCat-Video-Avatar-1.5", AVATAR,
            ["base_model_int8/**", "lora/**", "scheduler/**",
             "whisper-large-v3/**", "vocal_separator/**"],
        ),
    ):
        print(f"Checking/downloading allowed components from {repo} ...", flush=True)
        target.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=repo, local_dir=str(target),
            allow_patterns=patterns, max_workers=5,
        )
        models.commit()
    report = inspection()
    models.commit()
    if not report["ready"]:
        raise RuntimeError(f"Incomplete model volume: {json.dumps(report)}")
    return report


@app.function(
    image=download_image, cpu=1, memory=2048, timeout=600,
    volumes={str(ROOT): models},
)
def doctor() -> dict:
    return inspection()


@app.function(
    image=render_image,
    gpu=GPU_NAME,
    cpu=8,
    memory=65536,
    timeout=3600,
    min_containers=0,
    max_containers=1,
    scaledown_window=2,
    volumes={
        str(ROOT): models.with_mount_options(read_only=True)
        if hasattr(models, "with_mount_options") else models
    },
)
def render_avatar(image_b64: str, audio_b64: str, prompt: str) -> dict:
    """One real 93-frame (~3.72s) French talking avatar, then vertical MP4."""
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
        ]
        print("Running official LongCat Avatar v1.5, INT8, 480p, 1 segment ...", flush=True)
        completed = subprocess.run(
            cmd, cwd="/opt/LongCat-Video", text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3300,
            env={**os.environ, "OMP_NUM_THREADS": "4"},
        )
        if completed.returncode:
            raise RuntimeError("LongCat failed:\n" + completed.stdout[-8500:])
        candidates = sorted(output.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise RuntimeError("LongCat finished but output MP4 missing:\n" + completed.stdout[-3000:])
        raw = candidates[-1]
        final = folder / "avatar_vertical.mp4"
        # Official upstream inference is landscape; crop centrally to true 9:16
        # without stretching faces. Preserve speech and verify video/audio streams.
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(raw),
             "-vf", "crop=ih*9/16:ih,scale=720:1280",
             "-c:v", "libx264", "-crf", "19", "-preset", "fast",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
             str(final)], check=True, timeout=240,
        )
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
        wall = round(time.perf_counter() - started, 2)
        return {
            "video_b64": base64.b64encode(final.read_bytes()).decode("ascii"),
            "metadata": {
                "engine": "longcat-video-avatar-1.5",
                "gpu": GPU_NAME,
                "gpu_wall_seconds": wall,
                "duration_seconds": float(detail["format"]["duration"]),
                "bytes": final.stat().st_size,
                "streams": detail["streams"],
                "status": "real_generated_avatar_not_quality_reviewed",
            },
        }


@app.local_entrypoint()
def main(
    mode: str = "doctor",
    image_png: str = "benchmark_assets/character_reference.png",
    audio_wav: str = "artifacts/voice_fr.wav",
    out: str = "artifacts/longcat_avatar_fr.mp4",
    prompt: str = (
        "Photorealistic French man in his thirties, short dark hair, neat beard, "
        "anthracite sweater, subtle expressions, looking at camera, speaking "
        "French naturally in a modern dark premium tech studio, soft cinematic lighting"
    ),
):
    if mode == "prepare":
        result = prepare_models.remote()
        print(json.dumps(result, indent=2))
        return
    if mode == "doctor":
        result = doctor.remote()
        print(json.dumps(result, indent=2))
        if not result["ready"]:
            raise SystemExit("Models not ready: use --mode prepare")
        return
    if mode != "render":
        raise SystemExit("Allowed modes: prepare, doctor, render")
    photo = Path(image_png).read_bytes()
    voice = Path(audio_wav).read_bytes()
    result = render_avatar.remote(
        base64.b64encode(photo).decode("ascii"),
        base64.b64encode(voice).decode("ascii"),
        prompt,
    )
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(result["video_b64"]))
    meta = path.with_suffix(".json")
    meta.write_text(json.dumps(result["metadata"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Avatar saved: {path} ({path.stat().st_size} bytes); metadata: {meta}")
