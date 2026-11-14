"""Private two-frame comparison, adapted from the existing MAISON H3 worker."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from hashlib import sha256

import modal
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
VOLUME = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)
app = modal.App("terrainia-rust-h3-fl2va-private")
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


def build_graph(req: dict, reference: str | None = None, prefix: str = "pvs-h3", last_reference: str | None = None) -> dict:
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
    if last_reference:
        graph["2"] = n("LoadImage", image=last_reference)
        graph["104"]["inputs"]["last_frame"] = ["2", 0]
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
    with open("/tmp/pvs-h3-comfy.log", "wb") as log:
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


@app.function(image=gpu_image, gpu="L40S", cpu=8, memory=65536, timeout=900,
              scaledown_window=2, max_containers=1, retries=0,
              volumes={str(MOUNT): VOLUME})
def render_comparison(first_png: bytes, audio_wav: bytes, prompt: str) -> tuple[bytes, dict]:
    started = time.monotonic()
    proc = None
    audio_path = None
    try:
        proc = start_comfy()
        first = upload_png(first_png)
        if not audio_wav.startswith(b"RIFF") or len(audio_wav) > 450000:
            raise ValueError("Expected short original audio guide")
        audio_name = "noe-guide-" + uuid.uuid4().hex + ".wav"
        audio_path = COMFY / "input" / audio_name
        audio_path.parent.mkdir(exist_ok=True, parents=True)
        audio_path.write_bytes(audio_wav)
        req = {"width": 1280, "height": 720, "frames": 141, "seed": 128022, "steps": 20, "prompt": prompt}
        prefix = "terrainia-h3-" + uuid.uuid4().hex[:12]
        graph = build_graph(req, first, prefix)
        graph["105"] = {"class_type":"LoadAudio","inputs":{"audio":audio_name}}
        graph["106"] = {"class_type":"MiniMaxH3AddGuide","inputs":{
            "positive":["104",0],"latent":["104",1],"audio_vae":["24",0],
            "audio":["105",0],"frame_idx":0}}
        graph["16"]["inputs"]["conditioning"]=["106",0]
        graph["91"]["inputs"].pop("audio")
        del graph["23"]
        assert graph["104"]["inputs"]["first_frame"] == ["1", 0]
        assert graph["106"]["inputs"]["frame_idx"] == 0
        reply = http_json("/prompt", {"prompt": graph, "client_id": "terrainia-h3-pilot"}, timeout=60)
        out = wait_video(str(reply["prompt_id"]), prefix, proc)
        raw = out.read_bytes()
        if not 0 < len(raw) < 24 * 1024 * 1024:
            raise ValueError("Unexpected H3 video size")
        metadata = {
            "model": "MiniMax H3 FL2VA Pruned INT8 ConvRot + native timeline audio guide",
            "audio_guide_sha256": sha256(audio_wav).hexdigest(),
            "worker": "ComfyUI MAISON adaptation",
            "gpu": "L40S",
            "comfy_sha": COMFY_SHA,
            "checkpoint": FILES["diffusion_models"],
            "native_width": req["width"], "native_height": req["height"],
            "native_frames": req["frames"], "native_fps": 24,
            "seed": req["seed"], "steps": req["steps"],
            "gpu_worker_seconds": round(time.monotonic() - started, 2),
            "raw_sha256": sha256(raw).hexdigest(),
        }
        return raw, metadata
    except Exception as exc:
        # Only report exception type and stage. A model message can contain the private prompt.
        raise RuntimeError(f"H3 worker failed: {type(exc).__name__}") from None
    finally:
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
