"""English zero-shot voice cloning for the English talking-head production.

Uses the repository's existing Chatterbox Multilingual V3 adapter/model family.
The source MP3 is only a speaker reference; synthesis receives explicit new text.
"""
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
from pathlib import Path

import modal

APP_NAME = "pvs-english-voice"
PRIVATE_VOLUME_NAME = "pvs-english-talking-head-private"
PRIVATE_MOUNT = "/mnt/private-voice-artifacts"
private_artifacts = modal.Volume.from_name(PRIVATE_VOLUME_NAME, create_if_missing=True)
app = modal.App(APP_NAME)
model_cache = modal.Volume.from_name("pvs-english-voice-model-cache", create_if_missing=True)
image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04", add_python="3.11"
    )
    .apt_install("ffmpeg", "libsndfile1", "libgomp1")
    .pip_install("torch==2.6.0", index_url="https://download.pytorch.org/whl/cu124")
    .pip_install("chatterbox-tts", "torchaudio==2.6.0")
)


@app.function(image=image, cpu=8, memory=16384, timeout=1800,
              max_containers=1, scaledown_window=60,
              volumes={"/mnt/model-cache": model_cache})
def cpu_smoke() -> dict:
    """Load V3 and run a short English inference on CPU only; no portrait/audio input."""
    import os
    os.environ["HF_HOME"] = "/mnt/model-cache/huggingface"
    os.environ["HUGGINGFACE_HUB_CACHE"] = "/mnt/model-cache/huggingface/hub"
    import time
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    if torch.cuda.is_available():
        raise RuntimeError("CPU-only smoke test unexpectedly sees CUDA")
    started = time.perf_counter()
    model = ChatterboxMultilingualTTS.from_pretrained(device="cpu", t3_model="v3")
    audio = model.generate("A quick English voice check.", language_id="en")
    duration = float(audio.shape[-1]) / float(model.sr)
    model_cache.commit()
    return {"model": "Chatterbox Multilingual V3", "device": "cpu",
            "sample_rate": int(model.sr), "smoke_audio_seconds": round(duration, 3),
            "wall_seconds": round(time.perf_counter() - started, 2),
            "status": "CPU model-load-and-inference-smoke-test-passed"}


@app.function(image=image, gpu="A10G", cpu=4, memory=16384, timeout=900,
              max_containers=1, scaledown_window=60,
              volumes={PRIVATE_MOUNT: private_artifacts,
                       "/mnt/model-cache": model_cache})
def synthesize(reference_b64: str, text: str, artifact_name: str = "voice_sample.wav") -> dict:
    """Clone English voice from supplied MP3 and return speech WAV + timing metadata."""
    import os
    os.environ["HF_HOME"] = "/mnt/model-cache/huggingface"
    os.environ["HUGGINGFACE_HUB_CACHE"] = "/mnt/model-cache/huggingface/hub"
    import torch
    import torchaudio
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    if not text.strip() or len(text) > 6000:
        raise ValueError("Synthesis text is empty or too long")
    source = base64.b64decode(reference_b64, validate=True)
    if len(source) > 15_000_000:
        raise ValueError("Reference audio is unexpectedly large")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pvs-en-voice-") as temp:
        root = Path(temp)
        reference = root / "reference.mp3"
        wav_ref = root / "reference.wav"
        reference.write_bytes(source)
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(reference), "-vn",
            "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(wav_ref),
        ], check=True, timeout=60)
        model = ChatterboxMultilingualTTS.from_pretrained(device="cuda", t3_model="v3")
        audio = model.generate(
            text, language_id="en", audio_prompt_path=str(wav_ref),
            exaggeration=0.45, cfg_weight=0.45,
        )
        output = root / "speech.wav"
        torchaudio.save(str(output), audio.cpu(), model.sr)
        duration = float(audio.shape[-1]) / float(model.sr)
        name = Path(artifact_name)
        if name.name != artifact_name or name.suffix.lower() != ".wav":
            raise ValueError("Artifact name must be a plain .wav filename")
        private_dir = Path(PRIVATE_MOUNT) / "english-talking-head-20261027"
        private_dir.mkdir(parents=True, exist_ok=True)
        private_path = private_dir / name.name
        private_path.write_bytes(output.read_bytes())
        private_artifacts.commit()
        result = {
            "audio_base64": base64.b64encode(output.read_bytes()).decode("ascii"),
            "duration_seconds": round(duration, 3),
            "sample_rate": int(model.sr),
            "model": "Chatterbox Multilingual V3",
            "language": "en",
            "gpu": "A10G",
            "gpu_wall_seconds": round(time.perf_counter() - started, 2),
            "private_volume": PRIVATE_VOLUME_NAME,
            "private_path": f"english-talking-head-20261027/{name.name}",
            "status": "generated_not_human_voice_reviewed",
        }
        return result


@app.local_entrypoint()
def main(mode: str = "synthesize", reference_mp3: str = "", text: str = "",
         out: str = "voice_sample.wav", artifact_name: str = "voice_sample.wav"):
    """CPU-smoke or synthesize; private Modal volume stores generated speech."""
    if mode == "cpu-check":
        print(json.dumps(cpu_smoke.remote(), ensure_ascii=False))
        return
    if mode != "synthesize":
        raise ValueError("mode must be cpu-check or synthesize")
    if not reference_mp3 or not text.strip():
        raise ValueError("synthesize mode requires --reference-mp3 and --text")
    source = Path(reference_mp3).read_bytes()
    response = synthesize.remote(base64.b64encode(source).decode("ascii"), text, artifact_name)
    destination = Path(out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(base64.b64decode(response.pop("audio_base64"), validate=True))
    destination.with_suffix(".json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"output": str(destination), **response}, ensure_ascii=False))
