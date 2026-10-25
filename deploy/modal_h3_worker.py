"""MiniMax H3 FL2VA on Modal, using native ComfyUI nodes. Separate from pvs-ltx.

CPU model staging stores only the four compact H3 files in pvs-minimax-h3-models.
GPU video call uses the existing studio contract:
    render_clip({"prompt", "duration_s", "aspect_ratio", "image_png_base64", ...})
    -> {"video_base64": MP4, "metadata": {...}}
No per-video API provider is used. Do not mix H3 files into the LTX volume.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import modal

APP_NAME = "pvs-minimax-h3"
VOLUME_NAME = "pvs-minimax-h3-models"
MOUNT = Path("/mnt/h3-models")
COMFY = Path("/opt/ComfyUI")
COMFY_URL = "http://127.0.0.1:8188"
COMFY_SHA = "19ae172bff6c9e4c738e7f2e00fe087f5b5b46ab"
FILES = {
    "diffusion_models": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "text_encoders": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae_video": "minimax_h3_video_vae_int8_convrot.safetensors",
    "vae_audio": "minimax_h3_audio_vae_fp32.safetensors",
}
SIZES_MIN = {
    "diffusion_models": 15_000_000_000,
    "text_encoders": 11_000_000_000,
    "vae_video": 2_000_000_000,
    "vae_audio": 400_000_000,
}
VOLUME = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
app = modal.App(APP_NAME)
prep_image = modal.Image.debian_slim(python_version="3.12").pip_install("huggingface_hub>=0.34,<2")
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "libsm6")
    .pip_install("torch==2.8.0", index_url="https://download.pytorch.org/whl/cu128")
    .run_commands(
        "git init /opt/ComfyUI",
        "git -C /opt/ComfyUI remote add origin https://github.com/Comfy-Org/ComfyUI.git",
        f"git -C /opt/ComfyUI fetch --depth 1 origin {COMFY_SHA}",
        f"git -C /opt/ComfyUI checkout --detach {COMFY_SHA}",
        "pip install --no-cache-dir -r /opt/ComfyUI/requirements.txt "
        "torch==2.8.0 --extra-index-url https://download.pytorch.org/whl/cu128",
    )
)


def model_files() -> dict[str, Path]:
    return {
        k: MOUNT / ("vae" if k.startswith("vae_") else k) / filename
        for k, filename in FILES.items()
    }


def verify_models() -> dict:
    files = {}
    for key, path in model_files().items():
        size = path.stat().st_size if path.is_file() else 0
        files[key] = {"exists": size >= SIZES_MIN[key], "bytes": size, "filename": path.name}
    return {"app": APP_NAME, "volume": VOLUME_NAME, "files": files,
            "ready": all(x["exists"] for x in files.values())}


@app.function(image=prep_image, cpu=2, memory=4096, timeout=180)
def doctor() -> dict:
    """No GPU. Verify volume and all four selected weights."""
    return verify_models()


@app.function(image=prep_image, cpu=4, memory=16384, timeout=3600, volumes={str(MOUNT): VOLUME})
def prepare() -> dict:
    """CPU-only one-time download: four exact files, no full 525GB snapshot."""
    from huggingface_hub import hf_hub_download
    for key, target in model_files().items():
        if target.is_file() and target.stat().st_size >= SIZES_MIN[key]:
            print(f"Already staged {key}: {target.stat().st_size} bytes", flush=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        print(f"Staging {key} from Comfy-Org/MiniMax-H3", flush=True)
        hf_hub_download(
            repo_id="Comfy-Org/MiniMax-H3",
            filename=target.relative_to(MOUNT).as_posix(),
            local_dir=str(MOUNT),
        )
        if not target.is_file() or target.stat().st_size < SIZES_MIN[key]:
            raise RuntimeError(f"Incomplete {key}: expected at least {SIZES_MIN[key]} bytes")
        VOLUME.commit()
    report = verify_models()
    if not report["ready"]:
        raise RuntimeError("H3 model volume not ready")
    return report


def validate(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Expected request object")
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt or len(prompt) > 7000:
        raise ValueError("Prompt missing or too long")
    duration = float(payload.get("duration_s", 5))
    if not 4 <= duration <= 15:
        raise ValueError("H3 clip duration must be 4-15 s")
    aspect = str(payload.get("aspect_ratio") or "9:16")
    sizes = {"9:16": (768, 1344), "16:9": (1344, 768), "1:1": (1024, 1024)}
    if aspect not in sizes:
        raise ValueError("H3 aspect must be 9:16, 16:9 or 1:1")
    # Official grid: 17k+5 at 24fps.
    desired = round(duration * 24)
    frames = max(5, desired) + (5 - max(5, desired) % 17) % 17
    if frames > 362:
        frames = 362
    ref = payload.get("image_png_base64")
    if ref is not None:
        if not isinstance(ref, str):
            raise ValueError("Reference must be a Base64 PNG")
        blob = base64.b64decode(ref, validate=True)
        if not blob.startswith(b"\x89PNG\r\n\x1a\n") or len(blob) > 24 * 1024 * 1024:
            raise ValueError("Reference image must be PNG <=24MiB")
    return {"prompt": prompt, "duration_s": duration, "frames": frames,
            "width": sizes[aspect][0], "height": sizes[aspect][1],
            "aspect_ratio": aspect, "image_png_base64": ref,
            "seed": int(payload.get("seed", 42)), "steps": int(payload.get("steps", 20)),
            "audio_mode": str(payload.get("audio_mode", "native"))}


def build_graph(req: dict, reference: str | None = None, prefix: str = "pvs-h3") -> dict:
    """Native-node, one-pass H3 I2V graph based on Comfy-Org official template."""
    n = lambda cls, **inputs: {"class_type": cls, "inputs": inputs}
    graph = {
        "6": n("UNETLoader", unet_name=FILES["diffusion_models"], weight_dtype="default"),
        "11": n("VAELoader", vae_name=FILES["vae_video"]),
        "24": n("VAELoader", vae_name=FILES["vae_audio"]),
        "13": n("CLIPLoader", clip_name=FILES["text_encoders"], type="minimax", device="default"),
        "104": n("MiniMaxH3ImageToVideo", clip=["13", 0], vae=["11", 0],
                 prompt=req["prompt"], width=req["width"], height=req["height"],
                 length=req["frames"]),
        "15": n("RandomNoise", noise_seed=req["seed"]),
        "16": n("BasicGuider", model=["6", 0], conditioning=["104", 0]),
        "17": n("KSamplerSelect", sampler_name="res_multistep"),
        "9": n("BasicScheduler", model=["6", 0], scheduler="simple", steps=req["steps"], denoise=1.0),
        "14": n("SamplerCustomAdvanced", noise=["15", 0], guider=["16", 0],
                sampler=["17", 0], sigmas=["9", 0], latent_image=["104", 1]),
        "10": n("VAEDecode", samples=["14", 0], vae=["11", 0]),
        "23": n("VAEDecodeAudio", samples=["14", 0], vae=["24", 0]),
        "91": n("CreateVideo", images=["10", 0], audio=["23", 0], fps=24),
        "92": n("SaveVideo", video=["91", 0], filename_prefix=prefix,
                format="auto", codec="auto"),
    }
    if reference:
        graph["1"] = n("LoadImage", image=reference)
        graph["104"]["inputs"]["first_frame"] = ["1", 0]
    return graph


def http_json(path: str, obj: dict | None = None, timeout=30):
    req = urllib.request.Request(COMFY_URL + path,
                                 data=json.dumps(obj).encode() if obj is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def start_comfy():
    for key, src in model_files().items():
        if not src.is_file() or src.stat().st_size < SIZES_MIN[key]:
            raise RuntimeError(f"Missing H3 weight: {key} (run prepare first)")
        folder = "vae" if key.startswith("vae_") else key
        dest = COMFY / "models" / folder / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.symlink_to(src)
    log = open("/tmp/pvs-h3-comfy.log", "wb")
    proc = subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1",
                             "--port", "8188", "--disable-auto-launch", "--lowvram"],
                            cwd=COMFY, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(180):
        if proc.poll() is not None:
            raise RuntimeError("ComfyUI H3 boot failure (see Modal logs)")
        try:
            http_json("/system_stats", timeout=3)
            return proc
        except Exception:
            time.sleep(2)
    proc.terminate()
    raise TimeoutError("ComfyUI did not start within 6 minutes")


def upload_png(blob: bytes) -> str:
    boundary = "pvs" + uuid.uuid4().hex
    name = "pvs-h3-" + uuid.uuid4().hex + ".png"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            "Content-Type: image/png\r\n\r\n").encode() + blob + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(COMFY_URL + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        ans = json.load(resp)
    return str(ans["name"])


def wait_video(task_id: str, prefix: str, proc: subprocess.Popen) -> Path:
    out = (COMFY / "output").resolve()
    for _ in range(1800):
        if proc.poll() is not None:
            raise RuntimeError("ComfyUI exited during MiniMax H3 render")
        entry = http_json("/history/" + urllib.parse.quote(task_id, safe="")).get(task_id, {})
        status = entry.get("status") or {}
        if status.get("status_str") == "error":
            raise RuntimeError("ComfyUI H3 generation error: " + repr(status.get("messages", []))[:2000])
        if status.get("completed"):
            for item in (entry.get("outputs") or {}).values():
                for key in ("videos", "gifs", "images", "files"):
                    for file in item.get(key) or []:
                        p = (out / str(file.get("subfolder") or "") / str(file.get("filename"))).resolve()
                        if p.is_relative_to(out) and p.suffix.lower() == ".mp4" and p.is_file() and p.stat().st_size:
                            return p
            found = list(out.glob(prefix + "*.mp4"))
            if found:
                return max(found, key=lambda p: p.stat().st_mtime_ns)
        time.sleep(2)
    raise TimeoutError("H3 render timed out")


@app.function(image=gpu_image, gpu="L40S", cpu=8, memory=65536, timeout=5400,
              scaledown_window=2, max_containers=1,
              volumes={str(MOUNT): VOLUME})
def render_clip(payload: dict) -> dict:
    request = validate(payload)
    started = time.monotonic()
    process = start_comfy()
    reference = None
    if request["image_png_base64"]:
        reference = upload_png(base64.b64decode(request["image_png_base64"], validate=True))
    prefix = "pvs-h3-" + uuid.uuid4().hex[:12]
    submitted = http_json("/prompt", {"prompt": build_graph(request, reference, prefix),
                                     "client_id": "pvs-h3"})
    task = str(submitted["prompt_id"])
    out = wait_video(task, prefix, process)
    data = out.read_bytes()
    if len(data) > 80 * 1024 * 1024:
        raise RuntimeError("H3 output too large for Base64 job contract (80 MiB max)")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type,width,height",
                            "-of", "json", str(out)], capture_output=True, text=True, check=True)
    report = json.loads(probe.stdout)
    if not any(s.get("codec_type") == "video" for s in report.get("streams", [])):
        raise RuntimeError("H3 output has no video track")
    metadata = {"engine": "minimax_h3", "gpu": "L40S",
                "width": request["width"], "height": request["height"],
                "frames": request["frames"],
                "duration_sec": float(report.get("format", {}).get("duration") or 0),
                "has_audio": any(s.get("codec_type") == "audio" for s in report.get("streams", [])),
                "generation_seconds": round(time.monotonic() - started, 2),
                "comfy_sha": COMFY_SHA, "checkpoint": FILES["diffusion_models"]}
    return {"video_base64": base64.b64encode(data).decode("ascii"), "metadata": metadata}


@app.local_entrypoint()
def main(mode: str = "doctor", output: str = ""):
    fn = {"doctor": doctor, "prepare": prepare}.get(mode)
    if fn is None:
        raise ValueError("mode must be doctor or prepare; render through Studio or Actions")
    result = fn.remote()
    print(json.dumps(result, indent=2))
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(result, indent=2))
