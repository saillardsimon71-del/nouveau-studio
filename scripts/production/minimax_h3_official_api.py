#!/usr/bin/env python3
"""Official MiniMax H3 hosted API adapter. NO local weights, NO Modal GPU.

H3 Community License excludes the EU for self-hosted weights absent explicit
authorization. Use the provider-hosted, pay-as-you-go API from France instead.
The preflight command is pure CPU and sends NO external requests.
Official docs: https://platform.minimax.io/docs/api-reference/video-generation-v2-create
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.minimax.io"
MODELS = ("MiniMax-H3", "MiniMax-H3-Highspeed", "MiniMax-H3-Lite", "MiniMax-H3-Max")
RESOLUTIONS = {
    "MiniMax-H3": ("768P", "2K"),
    "MiniMax-H3-Highspeed": ("768P",),
    "MiniMax-H3-Lite": ("480P", "768P"),
    "MiniMax-H3-Max": ("480P", "768P"),
}
DEFAULT_PROMPT = (
    "Luxury fashion film for an entirely fictional clothing house. An elegant model "
    "from the authentic editorial photograph maintains the exact outfit, accessories, "
    "facial identity and location, makes a subtle confident head turn, then calmly "
    "looks toward the lens. Sophisticated high-fashion lighting, controlled camera "
    "push-in, realistic fabric and anatomy, no brand marks, no new objects, no text."
)


def public_https(url: str) -> bool:
    try:
        p = urllib.parse.urlparse(url)
        host = (p.hostname or "").lower()
        if p.scheme != "https" or not host or p.username or p.password:
            return False
        if host in ("localhost", "127.0.0.1", "::1") or host.endswith((".local", ".internal")):
            return False
        import ipaddress
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except ValueError:
        return False


def build_payload(
    *, prompt: str, image_url: str = "", duration: int = 5,
    resolution: str = "768P", model: str = "MiniMax-H3",
    ratio: str = "9:16",
) -> dict:
    if model not in MODELS:
        raise ValueError(f"Unsupported model: {model}")
    if resolution not in RESOLUTIONS[model]:
        raise ValueError(f"Resolution {resolution} unavailable on {model}")
    if not (4 <= duration <= 15) or (model == "MiniMax-H3-Max" and duration < 5):
        raise ValueError("Duration unsupported for selected model")
    if not prompt.strip() or len(prompt) > 7000:
        raise ValueError("Prompt must be between 1 and 7000 characters")
    if ratio not in ("9:16", "16:9", "1:1", "4:3", "3:4", "21:9"):
        raise ValueError("Unsupported aspect ratio")
    content = [{"type": "text", "text": prompt.strip()}]
    if image_url:
        if not public_https(image_url):
            raise ValueError("First-frame image must have a public HTTPS URL")
        content.append({
            "type": "image_url", "image_url": {"url": image_url},
            "role": "first_frame",
        })
    return {
        "model": model,
        "content": content,
        "resolution": resolution,
        "duration": duration,
        "ratio": "adaptive" if image_url else ratio,
    }


def request_json(method: str, path: str, token: str, data: dict | None = None) -> dict:
    # Fixed trusted API origin and fixed paths; no user-controlled API host.
    url = API + path
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=50) as resp:
            obj = json.loads(resp.read(2_000_000))
            if not isinstance(obj, dict):
                raise RuntimeError("MiniMax response was not a JSON object")
            return obj
    except urllib.error.HTTPError as exc:
        # Never log the API key, request headers or prompt by accident.
        raise RuntimeError(f"MiniMax API HTTP {exc.code}; no video submitted/downloaded") from None


def download_mp4(url: str, destination: pathlib.Path) -> int:
    if not public_https(url):
        raise ValueError("MiniMax task returned a non-public/non-HTTPS video URL")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".partial")
    size = 0
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "SiteQuiVend-H3/1.0"}), timeout=120) as resp:
            with temp.open("wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > 150_000_000:
                        raise RuntimeError("Video exceeded 150MB download limit")
                    f.write(chunk)
        if size < 10_000:
            raise RuntimeError("MiniMax result is too small to be a video")
        temp.replace(destination)
        return size
    finally:
        temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("preflight", "render"), default="preflight")
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    p.add_argument("--image-url", default="", help="Actual licensed photograph, public HTTPS link; NEVER AI-generated still")
    p.add_argument("--duration", type=int, default=5)
    p.add_argument("--resolution", default="768P")
    p.add_argument("--model", default="MiniMax-H3")
    p.add_argument("--aspect", default="9:16")
    p.add_argument("--confirm-spend", default="non")
    p.add_argument("--out", default="artifacts/minimax_h3_test.mp4")
    p.add_argument("--max-wait-sec", type=int, default=2400)
    a = p.parse_args(argv)
    payload = build_payload(
        prompt=a.prompt, image_url=a.image_url, duration=a.duration,
        resolution=a.resolution, model=a.model, ratio=a.aspect,
    )
    # Do not echo photo URL or prompt, which may contain private creative details.
    summary = {
        "model": a.model, "resolution": a.resolution, "duration_sec": a.duration,
        "mode": a.mode, "uses_real_reference": bool(a.image_url),
        "request_is_chargeable": a.mode == "render",
        "self_hosted": False,
        "api": "Official MiniMax pay-as-you-go",
    }
    if a.mode == "preflight":
        print(json.dumps(summary, ensure_ascii=False))
        print("PREFLIGHT OK: API request schema validated, 0 API calls, 0 GPU used.")
        return 0
    if a.confirm_spend != "oui":
        raise RuntimeError("Paid render is disabled until --confirm-spend oui")
    token = os.environ.get("MINIMAX_API_KEY", "")
    if not token:
        raise RuntimeError("Missing MINIMAX_API_KEY GitHub Actions secret; no request sent")
    if not 60 <= a.max_wait_sec <= 3600:
        raise ValueError("max-wait-sec outside 60..3600")
    task_resp = request_json("POST", "/v2/video_generation", token, payload)
    task_id = str(task_resp.get("task_id", "")).strip()
    if not task_id.isdigit():
        raise RuntimeError("MiniMax returned no numeric task_id")
    print("Submitted official MiniMax H3 generation. Task ID: " + task_id)
    deadline = time.monotonic() + a.max_wait_sec
    last_status = None
    while time.monotonic() < deadline:
        result = request_json("GET", "/v2/query/video_generation/" + task_id, token)
        task = result.get("task", {})
        status = str(task.get("status", "")).lower()
        if status != last_status:
            print("Task status: " + (status or "unknown"))
            last_status = status
        if status == "succeeded":
            url = (task.get("content") or {}).get("url", "")
            if not url:
                raise RuntimeError("Task succeeded, but no video URL returned")
            out = pathlib.Path(a.out)
            size = download_mp4(url, out)
            metadata = {**summary, "task_id": task_id, "status": "succeeded", "bytes": size,
                        "video_file": out.name, "reported_usage": task.get("usage", {})}
            out.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            print("MP4 downloaded: " + str(out) + " (" + str(size) + " bytes)")
            return 0
        if status in ("failed", "cancelled", "canceled"):
            raise RuntimeError("MiniMax task failed or cancelled: " + task_id)
        time.sleep(12)
    raise RuntimeError("Timed out waiting for MiniMax task " + task_id + "; check billing/task status before retrying")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
