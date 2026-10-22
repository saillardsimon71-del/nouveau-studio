"""Modal worker — LTX-2.5 video generation for Premium Video Studio.

This app is **new** (`pvs-ltx`). It does not touch, redeploy or overwrite any
Studio IA application. It only *reads* the model volume that Studio IA V2 left
behind, read-only, because downloading the same ~40 GiB again would be waste.

Why ComfyUI and not `ltx_pipelines` (the native CLI): the weights already on the
shared volume are the **ComfyUI INT8-convrot** variants, not the full bf16
safetensors the native CLI expects. The ComfyUI path is the one that actually
rendered clips in Studio IA V2 (measured there: 78 s hot, 151-197 s cold, for
145 frames at 768x1344 on L40S). Reusing it means zero download for the first
real MP4. The native DFR path stays a later option; it needs its own volume and
a ~66 GiB download.

Everything is pinned:
  * LTX-2.5   Lightricks/LTX-2.5 @ 49b093a39c19169a8a81721dcc541e07e945232f
  * ComfyUI   d49e888586dd8ae012c0667b33466b815fee07f7
  * PyTorch   2.8.0 + cu128
  * graph     distilled 8 steps + spatial upsampler x2 (two passes)

Deploy (never from the Arena sandbox — it has no route to Modal):
    modal deploy deploy/modal_ltx_worker.py

Deploy-time overrides:
    PVS_MODAL_APP          default pvs-ltx
    PVS_MODAL_LTX_VOLUME   default studio-ltx25-models
    PVS_MODAL_GPU          default L40S (also RTX-PRO-6000, A100-80GB, H100)
"""

from __future__ import annotations

import base64
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import modal

APP_NAME = os.getenv("PVS_MODAL_APP", "pvs-ltx")
LTX_VOLUME_NAME = os.getenv("PVS_MODAL_LTX_VOLUME", "studio-ltx25-models")
GPU = os.getenv("PVS_MODAL_GPU", "L40S")

LTX_MODEL_REVISION = "49b093a39c19169a8a81721dcc541e07e945232f"
LTX_COMFYUI_REVISION = "d49e888586dd8ae012c0667b33466b815fee07f7"
LTX_VIDEO_CFG = 1.0
# The old project learned that forbidding "subtitles" in the prompt does not
# remove burned-in text; describing the scene does. This stays a negative only.
LTX_NEGATIVE_PROMPT = "background music, subtitles, text overlays, voiceover narration"

LTX_MODEL_FILES = {
    "unet": "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
    "clip": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
    "video_vae": "ltx-2.5-video-vae-conv-bf16.safetensors",
    "audio_vae": "ltx-2.5-audio-vae-bf16.safetensors",
    "upscaler": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
}
LTX_FOLDERS = {
    "unet": "diffusion_models",
    "clip": "text_encoders",
    "video_vae": "vae",
    "audio_vae": "vae",
    "upscaler": "latent_upscale_models",
}

LTX_FPS = 24
LTX_STEPS = 8
LTX_MIN_FRAMES = 25
LTX_MAX_FRAMES = 361  # 15.04 s @ 24 fps
LTX_SIZES = {"9:16": (768, 1344), "16:9": (1344, 768), "1:1": (1024, 1024)}

MODELS_MOUNT = Path("/mnt/ltx-models")
COMFYUI_DIR = Path(os.getenv("PVS_COMFYUI_DIR", "/opt/ComfyUI"))
COMFY_API = "http://127.0.0.1:8188"

app = modal.App(APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "libsm6", "libxext6")
    .pip_install("torch==2.8.0", index_url="https://download.pytorch.org/whl/cu128")
    .run_commands(
        "git init /opt/ComfyUI",
        "git -C /opt/ComfyUI remote add origin https://github.com/Comfy-Org/ComfyUI.git",
        f"git -C /opt/ComfyUI fetch --depth 1 origin {LTX_COMFYUI_REVISION}",
        f"git -C /opt/ComfyUI checkout --detach {LTX_COMFYUI_REVISION}",
        "pip install --no-cache-dir -r /opt/ComfyUI/requirements.txt "
        "torch==2.8.0 --extra-index-url https://download.pytorch.org/whl/cu128",
    )
    .env({"PVS_COMFYUI_DIR": "/opt/ComfyUI"})
)


# ---------------------------------------------------------------------------
# Request contract
# ---------------------------------------------------------------------------
def frames_for_duration(seconds: float) -> int:
    """Round a duration up onto LTX's 8k+1 frame grid (the V2 rule).

    Rounding *up* keeps the requested duration instead of truncating it: 5 s of
    frames (120) becomes 121 frames = 5.04 s. Clamped to the 25-361 frames the
    distilled LTX-2.5 graph supports.
    """
    if not math.isfinite(float(seconds)) or float(seconds) <= 0:
        raise ValueError("duration must be positive and finite")
    requested = max(LTX_MIN_FRAMES, math.ceil(float(seconds) * LTX_FPS))
    frames = requested + (1 - requested) % 8
    return min(LTX_MAX_FRAMES, frames)


def validate(payload: dict) -> dict:
    """Normalise and validate a request; returns the resolved request."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is empty")
    if len(prompt) > 6000:
        raise ValueError("prompt too long (6000 chars max)")

    aspect = str(payload.get("aspect_ratio") or "9:16")
    if aspect not in LTX_SIZES:
        raise ValueError(f"unknown aspect_ratio {aspect!r} (9:16, 16:9, 1:1)")
    width, height = LTX_SIZES[aspect]

    try:
        duration = float(payload.get("duration_s") or 5.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration_s must be a number") from exc
    if not 1.0 <= duration <= 15.0:
        raise ValueError("duration_s must be within 1.0-15.0 s (LTX-2.5 limit)")
    frames = frames_for_duration(duration)

    seed = payload.get("seed", 42)
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("seed must be an unsigned 64-bit integer")

    audio_mode = str(payload.get("audio_mode") or "native")
    if audio_mode not in ("native", "silent"):
        raise ValueError("audio_mode must be 'native' or 'silent'")

    image_b64 = payload.get("image_png_base64")
    if image_b64 is not None:
        if not isinstance(image_b64, str) or not image_b64:
            raise ValueError("image_png_base64 must be a non-empty string")
        try:
            content = base64.b64decode(image_b64, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("image_png_base64 is not valid base64") from exc
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("reference image must be a PNG")
        if len(content) > 24 * 1024 * 1024:
            raise ValueError("reference image larger than 24 MiB")

    strength = float(payload.get("image_strength", 0.7))
    if not 0.0 <= strength <= 1.0:
        raise ValueError("image_strength must be within 0.0-1.0")

    trace = payload.get("trace_id") or f"pvs-{uuid.uuid4().hex[:12]}"
    if not isinstance(trace, str) or len(trace) > 96 or not trace.replace("-", "").replace("_", "").isalnum():
        raise ValueError("trace_id must be alphanumeric (96 chars max)")

    return {
        "prompt": prompt,
        "aspect_ratio": aspect,
        "width": width,
        "height": height,
        "fps": LTX_FPS,
        "frames": frames,
        "duration_s": round(frames / LTX_FPS, 3),
        "steps": LTX_STEPS,
        "seed": seed,
        "audio_mode": audio_mode,
        "image_png_base64": image_b64,
        "image_strength": strength,
        "trace_id": trace,
    }


# ---------------------------------------------------------------------------
# ComfyUI graph (LTX-2.5 two passes)
# ---------------------------------------------------------------------------
def build_graph(request: dict, *, output_prefix: str, uploaded_image: str | None = None) -> dict:
    if not output_prefix or output_prefix.startswith("/") or ".." in output_prefix.split("/"):
        raise ValueError("invalid output prefix")

    def node(kind: str, **inputs):
        return {"class_type": kind, "inputs": inputs}

    graph = {
        "6": node("UNETLoader", unet_name=LTX_MODEL_FILES["unet"], weight_dtype="default"),
        "11": node("VAELoader", vae_name=LTX_MODEL_FILES["video_vae"]),
        "24": node("VAELoader", vae_name=LTX_MODEL_FILES["audio_vae"]),
        "13": node("CLIPLoader", clip_name=LTX_MODEL_FILES["clip"], type="ltxv", device="default"),
        "20": node("CLIPTextEncode", clip=["13", 0], text=request["prompt"]),
        "21": node("CLIPTextEncode", clip=["13", 0], text=LTX_NEGATIVE_PROMPT),
        "22": node("LTXVConditioning", positive=["20", 0], negative=["21", 0], frame_rate=request["fps"]),
        "30": node(
            "EmptyLTXVLatentVideo",
            width=request["width"] // 2,
            height=request["height"] // 2,
            length=request["frames"],
            batch_size=1,
        ),
        "32": node(
            "LTXVEmptyLatentAudio",
            audio_vae=["24", 0],
            frames_number=request["frames"],
            frame_rate=request["fps"],
            batch_size=1,
        ),
        "33": node("LTXVConcatAVLatent", video_latent=["30", 0], audio_latent=["32", 0]),
        "15": node("RandomNoise", noise_seed=request["seed"]),
        "16": node(
            "LTXVDualCFGGuider",
            model=["6", 0],
            positive=["22", 0],
            negative=["22", 1],
            video_cfg=LTX_VIDEO_CFG,
            audio_cfg=1.0,
        ),
        "17": node("KSamplerSelect", sampler_name="euler_ancestral"),
        "9": node(
            "ManualSigmas",
            sigmas="1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0",
        ),
        "14": node(
            "SamplerCustomAdvanced",
            noise=["15", 0],
            guider=["16", 0],
            sampler=["17", 0],
            sigmas=["9", 0],
            latent_image=["33", 0],
        ),
        "34": node("LTXVSeparateAVLatent", av_latent=["14", 0]),
        "35": node("LatentUpscaleModelLoader", model_name=LTX_MODEL_FILES["upscaler"]),
        "36": node("LTXVLatentUpsampler", samples=["34", 0], upscale_model=["35", 0], vae=["11", 0]),
        "38": node("LTXVConcatAVLatent", video_latent=["36", 0], audio_latent=["34", 1]),
        "39": node("RandomNoise", noise_seed=42),
        "40": node("ManualSigmas", sigmas="0.85, 0.7250, 0.4219, 0.0"),
        "41": node(
            "SamplerCustomAdvanced",
            noise=["39", 0],
            guider=["16", 0],
            sampler=["17", 0],
            sigmas=["40", 0],
            latent_image=["38", 0],
        ),
        "42": node("LTXVSeparateAVLatent", av_latent=["41", 0]),
        "10": node(
            "VAEDecodeTiled",
            samples=["42", 0],
            vae=["11", 0],
            tile_size=512,
            overlap=64,
            temporal_size=64,
            temporal_overlap=16,
        ),
        "91": node("CreateVideo", images=["10", 0], fps=request["fps"]),
        "92": node("SaveVideo", video=["91", 0], filename_prefix=output_prefix, format="auto", codec="auto"),
    }
    if uploaded_image:
        graph["1"] = node("LoadImage", image=uploaded_image)
        graph["2"] = node("LTXVPreprocess", image=["1", 0], img_compression=18)
        graph["31"] = node(
            "LTXVImgToVideoInplace",
            vae=["11", 0],
            image=["2", 0],
            latent=["30", 0],
            strength=request["image_strength"],
            bypass=False,
        )
        graph["33"]["inputs"]["video_latent"] = ["31", 0]
        graph["37"] = node(
            "LTXVImgToVideoInplace",
            vae=["11", 0],
            image=["2", 0],
            latent=["36", 0],
            strength=1.0,
            bypass=False,
        )
        graph["38"]["inputs"]["video_latent"] = ["37", 0]
    if request.get("audio_mode") == "native":
        graph["23"] = node("LTXVAudioVAEDecode", samples=["42", 1], audio_vae=["24", 0])
        graph["91"]["inputs"]["audio"] = ["23", 0]
    return graph


# ---------------------------------------------------------------------------
# Runtime helpers (inside the container)
# ---------------------------------------------------------------------------
def _volume():
    """Resolve the shared volume lazily, read-only.

    Lazy so that `modal deploy` succeeds even if the volume is absent; the
    `doctor()` function then reports the real problem instead of the import
    failing with a traceback nobody can read from a phone.
    """
    volume = modal.Volume.from_name(LTX_VOLUME_NAME, create_if_missing=False)
    options = getattr(volume, "with_mount_options", None)
    return options(read_only=True) if callable(options) else volume


def mount_models() -> dict:
    """Symlink the five read-only weights into ComfyUI's model folders."""
    mounted = {}
    for key, folder in LTX_FOLDERS.items():
        source = MODELS_MOUNT / folder / LTX_MODEL_FILES[key]
        if not source.is_file():
            raise RuntimeError(
                f"poids LTX absent du volume: {source}\n"
                "Vérifier PVS_MODAL_LTX_VOLUME et l'état du volume (fonction doctor)."
            )
        target = COMFYUI_DIR / "models" / folder / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.symlink_to(source)
        mounted[key] = {"path": str(source), "bytes": source.stat().st_size}
    return mounted


def _http_json(route: str, body: dict | None = None, timeout: int = 60) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        COMFY_API + route, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def _log_tail(path: Path, limit: int = 6000) -> str:
    try:
        with path.open("rb") as log:
            log.seek(max(0, path.stat().st_size - limit))
            return log.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


_comfy_process: subprocess.Popen | None = None
_comfy_log = Path("/tmp/pvs-comfyui.log")


def _stop_comfy() -> None:
    global _comfy_process
    process, _comfy_process = _comfy_process, None
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()


def _start_comfy() -> float:
    global _comfy_process
    mount_models()
    started = time.monotonic()
    with _comfy_log.open("wb") as log:
        _comfy_process = subprocess.Popen(
            [
                sys.executable,
                "main.py",
                "--listen",
                "127.0.0.1",
                "--port",
                "8188",
                "--disable-auto-launch",
                "--disable-comfy-compiler",
            ],
            cwd=COMFYUI_DIR,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        if _comfy_process.poll() is not None:
            raise RuntimeError("ComfyUI s'est arrêté au démarrage:\n" + _log_tail(_comfy_log))
        try:
            _http_json("/system_stats", timeout=5)
            return round(time.monotonic() - started, 3)
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(2)
    _stop_comfy()
    raise TimeoutError("ComfyUI n'a pas démarré en 420 s:\n" + _log_tail(_comfy_log))


def _ensure_comfy() -> tuple[float, bool]:
    if _comfy_process is not None and _comfy_process.poll() is None:
        try:
            _http_json("/system_stats", timeout=5)
            return 0.0, True
        except (urllib.error.URLError, TimeoutError, OSError):
            _stop_comfy()
    return _start_comfy(), False


def _wait_for_video(prompt_id: str, prefix: str) -> Path:
    """Poll ComfyUI until the MP4 exists on disk, not just when it says "done".

    ComfyUI reports completion slightly before the file is flushed, so the
    history alone is not enough: we also look for the file by name, with a 60 s
    grace period before declaring failure.
    """
    deadline = time.monotonic() + 4800
    artifact_deadline: float | None = None
    while time.monotonic() < deadline:
        if _comfy_process is not None and _comfy_process.poll() is not None:
            raise RuntimeError("ComfyUI s'est arrêté pendant la génération:\n" + _log_tail(_comfy_log))
        history = _http_json("/history/" + urllib.parse.quote(prompt_id, safe=""))
        entry = history.get(prompt_id, {})
        status = entry.get("status") or {}
        if status.get("status_str") == "error":
            raise RuntimeError("Échec du rendu LTX: " + repr(status.get("messages", []))[:4000])
        if status.get("completed") or status.get("status_str") in ("success", "completed"):
            if artifact_deadline is None:
                artifact_deadline = time.monotonic() + 60
            output_root = (COMFYUI_DIR / "output").resolve()
            for output in (entry.get("outputs") or {}).values():
                for key in ("images", "videos", "gifs", "files"):
                    for item in output.get(key) or []:
                        name = item.get("filename") or ""
                        if Path(name).suffix.lower() != ".mp4":
                            continue
                        path = (output_root / (item.get("subfolder") or "") / name).resolve()
                        if path.is_relative_to(output_root) and path.is_file() and path.stat().st_size > 0:
                            return path
            relative = Path(prefix)
            candidates = [
                path.resolve()
                for path in (output_root / relative.parent).glob(relative.name + "*.mp4")
                if path.is_file() and path.stat().st_size > 0
            ]
            if candidates:
                return max(candidates, key=lambda item: item.stat().st_mtime_ns)
            if time.monotonic() >= artifact_deadline:
                raise RuntimeError("ComfyUI a terminé sans produire de MP4 lisible en 60 s.")
        time.sleep(2)
    raise TimeoutError("Le rendu LTX n'a produit aucun MP4 dans le délai imparti")


def _probe_video(path: Path) -> dict:
    """ffprobe the produced MP4: never hand back an unreadable file."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError("MP4 illisible: " + result.stderr[-2000:])
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video:
        raise RuntimeError("MP4 sans piste vidéo")
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "video_codec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt"),
        "audio_codec": (audio or {}).get("codec_name"),
        "has_audio": audio is not None,
        "duration_sec": round(float(data.get("format", {}).get("duration") or 0), 3),
        "bytes": path.stat().st_size,
    }


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------
@app.function(
    image=image,
    cpu=1,
    memory=2048,
    timeout=600,
    scaledown_window=5,
    volumes={str(MODELS_MOUNT): _volume()},
)
def doctor() -> dict:
    """Zero-GPU diagnostic: which workspace am I in, is the volume usable?

    1 CPU, no GPU: this is how we answer "did I authenticate to the right Modal
    workspace, and are the LTX weights actually there?" without spending.
    """
    started = time.time()
    report: dict = {
        "app": APP_NAME,
        "gpu_configured": GPU,
        "volume_name": LTX_VOLUME_NAME,
        "modal_environment": os.getenv("MODAL_ENVIRONMENT"),
        "modal_task_id": os.getenv("MODAL_TASK_ID"),
        "modal_region": os.getenv("MODAL_REGION"),
        "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "comfyui_revision": LTX_COMFYUI_REVISION,
        "ltx_model_revision": LTX_MODEL_REVISION,
    }
    mount_ok = MODELS_MOUNT.is_dir()
    report["volume_mounted"] = mount_ok
    files: dict = {}
    total = 0
    if mount_ok:
        for key, folder in LTX_FOLDERS.items():
            path = MODELS_MOUNT / folder / LTX_MODEL_FILES[key]
            if path.is_file():
                size = path.stat().st_size
                total += size
                files[key] = {"present": True, "bytes": size, "file": path.name}
            else:
                files[key] = {"present": False, "file": path.name, "folder": folder}
    report["weights"] = files
    report["weights_present"] = sum(1 for item in files.values() if item.get("present"))
    report["weights_expected"] = len(LTX_MODEL_FILES)
    report["weights_total_bytes"] = total
    report["ready_for_ltx"] = report["weights_present"] == len(LTX_MODEL_FILES)
    report["doctor_seconds"] = round(time.time() - started, 3)
    return report


@app.function(
    image=image,
    gpu=GPU,
    cpu=8,
    memory=65536,
    timeout=5400,
    min_containers=0,
    max_containers=1,
    scaledown_window=2,
    volumes={str(MODELS_MOUNT): _volume()},
)
def render_clip(payload: dict) -> dict:
    """Generate one LTX-2.5 clip, one at a time, no automatic retry.

    Returns the MP4 as base64 plus phase timings so every second of GPU time can
    be attributed to container start / ComfyUI boot / render / probe.
    """
    request = validate(payload)
    started = time.perf_counter()
    phases: list[dict] = []

    def phase(name: str, since: float, detail: str = "") -> float:
        now = time.perf_counter()
        phases.append({"phase": name, "seconds": round(now - since, 3), "detail": detail})
        return now

    input_path: Path | None = None
    try:
        startup_seconds, reused = _ensure_comfy()
        phases.append({"phase": "COMFY_READY", "seconds": round(startup_seconds, 3), "detail": f"reused={reused}"})
        load_ready = time.perf_counter()

        uploaded = None
        if request["image_png_base64"]:
            content = base64.b64decode(request["image_png_base64"], validate=True)
            input_path = COMFYUI_DIR / "input" / f"pvs-{uuid.uuid4().hex}.png"
            input_path.parent.mkdir(parents=True, exist_ok=True)
            input_path.write_bytes(content)
            uploaded = input_path.name

        prefix = f"pvs/{request['trace_id']}"
        graph = build_graph(request, output_prefix=prefix, uploaded_image=uploaded)
        submitted = phase("GRAPH_BUILT", load_ready, f"{len(graph)} nodes")

        response = _http_json("/prompt", {"prompt": graph, "client_id": f"pvs-{uuid.uuid4().hex}"}, timeout=120)
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI a refusé le graphe: {json.dumps(response)[:2000]}")
        video_path = _wait_for_video(prompt_id, prefix)
        executed = phase("RENDERED", submitted, video_path.name)

        probe = _probe_video(video_path)
        phase("PROBED", executed)

        metadata = {
            **probe,
            "engine": "LTX-2.5 Distilled (ComfyUI, 2 passes)",
            "gpu": GPU,
            "app": APP_NAME,
            "trace_id": request["trace_id"],
            "seed": request["seed"],
            "steps": request["steps"],
            "width_requested": request["width"],
            "height_requested": request["height"],
            "frames": request["frames"],
            "fps": request["fps"],
            "duration_requested": request["duration_s"],
            "aspect_ratio": request["aspect_ratio"],
            "audio_mode": request["audio_mode"],
            "continuity_mode": "image" if uploaded else "none",
            "image_strength": request["image_strength"],
            "model_revision": LTX_MODEL_REVISION,
            "comfyui_revision": LTX_COMFYUI_REVISION,
            "video_cfg": LTX_VIDEO_CFG,
            "comfy_startup_seconds": startup_seconds,
            "comfy_reused": reused,
            "generation_seconds": round(time.perf_counter() - started, 3),
            "phases": phases,
        }
        return {
            "video_base64": base64.b64encode(video_path.read_bytes()).decode("ascii"),
            "metadata": metadata,
        }
    finally:
        if input_path is not None:
            try:
                input_path.unlink(missing_ok=True)
            except OSError:
                pass
        _stop_comfy()


# ---------------------------------------------------------------------------
# Local entrypoint — this is what GitHub Actions calls.
#
# `modal run` executes this on the *runner*, never in the container: it is the
# bridge between the workflow inputs and the GPU function. One entrypoint with a
# `mode` switch, so there is no ambiguity about which app is being targeted.
# ---------------------------------------------------------------------------
GPU_RATE_USD_PER_SEC = {
    "L40S": 0.000542,
    "RTX-PRO-6000": 0.000500,
    "A100-80GB": 0.000694,
    "H100": 0.001097,
}
CPU_RATE_USD_PER_SEC = 0.0000131 * 8  # 8 physical cores
RAM_RATE_USD_PER_SEC = 0.00000222 * 64  # 64 GiB


def _write_json(path: str, payload: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    return target


def estimate_cost_usd(gpu: str, seconds: float) -> float:
    """Rough cost from Modal's published rates and *measured* GPU seconds.

    Never presented as the invoice: the dashboard is the only source of truth.
    """
    return round(
        seconds
        * (
            GPU_RATE_USD_PER_SEC.get(gpu, 0.0)
            + CPU_RATE_USD_PER_SEC
            + RAM_RATE_USD_PER_SEC
        ),
        4,
    )


@app.local_entrypoint()
def main(
    mode: str = "doctor",
    prompt: str = "",
    duration: float = 3.0,
    aspect: str = "9:16",
    seed: int = 42,
    audio_mode: str = "native",
    image_png: str = "",
    image_strength: float = 0.7,
    json_out: str = "artifacts/doctor.json",
    out: str = "artifacts/clip.mp4",
):
    """`modal run deploy/modal_ltx_worker.py --mode doctor|render`."""
    if mode == "doctor":
        report = doctor.remote()
        _write_json(json_out, report)
        print(
            json.dumps(
                {
                    "app": report["app"],
                    "volume": report["volume_name"],
                    "weights_present": report["weights_present"],
                    "weights_expected": report["weights_expected"],
                    "ready_for_ltx": report["ready_for_ltx"],
                },
                indent=2,
            )
        )
        if not report["ready_for_ltx"]:
            missing = [key for key, value in report["weights"].items() if not value.get("present")]
            raise SystemExit(f"Volume incomplet, poids manquants : {missing}")
        return

    if mode != "render":
        raise SystemExit(f"mode inconnu : {mode!r} (doctor | render)")

    if not prompt.strip():
        raise SystemExit("--prompt est obligatoire pour un rendu")
    payload: dict = {
        "prompt": prompt,
        "duration_s": duration,
        "aspect_ratio": aspect,
        "seed": seed,
        "audio_mode": audio_mode,
        "image_strength": image_strength,
    }
    if image_png:
        content = Path(image_png).read_bytes()
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise SystemExit(f"{image_png} n'est pas un PNG")
        payload["image_png_base64"] = base64.b64encode(content).decode("ascii")
        print(f"image de référence : {image_png} ({len(content)} octets)")

    request = validate(payload)
    print(
        json.dumps(
            {
                "app": APP_NAME,
                "gpu": GPU,
                "volume": LTX_VOLUME_NAME,
                "resolved": {key: value for key, value in request.items() if key != "image_png_base64"},
            },
            indent=2,
        )
    )

    result = render_clip.remote(payload)
    metadata = result["metadata"]
    video_path = Path(out)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(base64.b64decode(result["video_base64"]))

    seconds = float(metadata.get("generation_seconds") or 0)
    metadata["cost_estimate_usd"] = estimate_cost_usd(GPU, seconds)
    metadata["cost_note"] = (
        "estimation à partir des tarifs publics Modal et des secondes mesurées ; "
        "la facture réelle est dans le dashboard"
    )
    metadata["artifact"] = str(video_path)
    _write_json(str(video_path.with_suffix(".json")), metadata)

    print(
        f"OK {video_path} — {metadata['bytes']} octets, {metadata['duration_sec']} s, "
        f"{seconds} s GPU, ~{metadata['cost_estimate_usd']} $"
    )
    print(f"pistes : vidéo={metadata['video_codec']} audio={metadata['audio_codec']}")
