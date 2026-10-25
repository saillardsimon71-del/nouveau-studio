#!/usr/bin/env python3
"""One isolated genuine-photo French native-voice H3 evaluation using own Modal L40S.

preflight: real Pexels photo + SHA256, no GPU.
render: exactly ONE direct pvs-minimax-h3.render_clip call at MAISON-01 settings.
inspect: ffprobe streams + non-silent audio RMS + visual contact sheet.
No MiniMax API, no AI-generated starting image, no retries, no site changes.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

from PIL import Image, ImageOps

OUTPUT = Path("artifacts/h3-french-voice")
PHOTO = {
    "pexels_id": 4382484,
    "photographer": "Anastasiya Gepp",
    "page": "https://www.pexels.com/photo/beautiful-woman-in-gray-top-looking-at-camera-4382484/",
    "url": "https://images.pexels.com/photos/4382484/pexels-photo-4382484.jpeg",
    "license": "https://www.pexels.com/license/",
    "caption": "Real studio portrait, adult woman with curly hair in a blazer, looking at camera.",
}
DIALOGUE = "Le vrai luxe, c'est de se sentir soi-même."
PROMPT = """For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1, 0.00s to 5.00s] A premium French-language advertising presenter is the adult woman from <Picture 1>. Preserve the EXACT original woman's facial identity, uncovered mouth, curly hair, blazer, background and natural photographic skin texture. She faces the lens in a clean close-up. She makes natural eye contact, inhales subtly and then speaks directly TO CAMERA, on screen, with one clear natural metropolitan-French female voice (S1), not voice-over. (S1) says in perfectly natural French with deliberate and convincing speech timing: <d>[French] Le vrai luxe, c'est de se sentir soi-même.</d> Her lips, jaw and mouth shapes are continuously and accurately synchronized to every French syllable. One subtle blink, precise realistic tongue/lip movements, a tiny confident smile after the final word. Very gentle cinematic camera push-in, balanced studio key and rim lighting, sophisticated human realism. Only the existing presenter is audible and visible. No subtitles, no written words, no new wardrobe or objects, no morphing, no cut. Finish the spoken sentence entirely before the shot ends.

overall_soundscape: The presenter's single clear synchronized French voice in a clean studio recording. Quiet low-level room tone, no other speakers and no overlapping voices.

non_diegetic_music: N/A
"""
VIDEO = OUTPUT / "H3-AVATAR-VOIX-FR-TEST.mp4"


def call(argv: list[str]) -> str:
    r = subprocess.run(argv, text=True, capture_output=True, check=False)
    if r.returncode:
        raise RuntimeError(f"Command {argv[0]} failed: " + r.stderr[-1600:])
    return r.stdout.strip()


def preflight():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(PHOTO["url"], headers={"User-Agent": "Mozilla/5.0 SiteQuiVend-Portrait/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read(25_000_001)
    if not (25_000 < len(raw) < 25_000_000):
        raise RuntimeError("Real photo download missing, invalid or too large")
    orig = OUTPUT / "pexels-source-original.jpg"
    orig.write_bytes(raw)
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    if min(image.size) < 720:
        raise ValueError(f"Source portrait too small for high-quality real frame: {image.size}")
    # Preserve the real photographed identity; no AI image transformations.
    crop = ImageOps.fit(image, (768, 1344), method=Image.Resampling.LANCZOS, centering=(0.5, 0.46))
    ref = OUTPUT / "pexels-real-firstframe.png"
    crop.save(ref, optimize=True)
    info = {
        **PHOTO, "original_px": list(image.size), "prepared_px": [768, 1344],
        "photo_original_sha256": hashlib.sha256(raw).hexdigest(),
        "prepared_photo_sha256": hashlib.sha256(ref.read_bytes()).hexdigest(),
        "dialogue": DIALOGUE,
        "model": "Comfy-Org/MiniMax-H3 self-hosted on pvs-minimax-h3 Modal L40S",
        "seed": 20261026, "duration_requested_s": 5, "steps": 20,
        "no_AI_generated_start_image": True, "no_paid_minimax_api": True,
        "noncommissioned_concept": True,
    }
    (OUTPUT / "provenance.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"PREFLIGHT PASS: real Pexels photo {image.size}, first frame 768x1344, no GPU", flush=True)


def render():
    ref = OUTPUT / "pexels-real-firstframe.png"
    if not ref.is_file():
        raise RuntimeError("Real keyframe required before any GPU spend")
    import modal
    fn = modal.Function.from_name("pvs-minimax-h3", "render_clip", environment_name="main").hydrate()
    print("Starting exactly ONE H3 native speech+video render at 20 steps. No API.", flush=True)
    result = fn.remote({
        "prompt": PROMPT,
        "duration_s": 5.0,
        "aspect_ratio": "9:16",
        "seed": 20261026,
        "steps": 20,
        "audio_mode": "native",
        "image_png_base64": base64.b64encode(ref.read_bytes()).decode("ascii"),
    })
    video_bytes = base64.b64decode(result["video_base64"], validate=True)
    if not (100_000 < len(video_bytes) < 40_000_000):
        raise RuntimeError("Unexpected H3 output size")
    VIDEO.write_bytes(video_bytes)
    (OUTPUT / "render-metadata.json").write_text(json.dumps(result.get("metadata", {}), indent=2), encoding="utf-8")
    print(f"REAL_H3_MP4={VIDEO} BYTES={len(video_bytes)}", flush=True)


def inspect():
    if not VIDEO.is_file() or VIDEO.stat().st_size < 100_000:
        raise RuntimeError("Missing actual H3 MP4; never fake audio/video")
    result = json.loads(call(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(VIDEO)]))
    vids = [s for s in result.get("streams", []) if s.get("codec_type") == "video"]
    auds = [s for s in result.get("streams", []) if s.get("codec_type") == "audio"]
    if not vids or not auds:
        raise RuntimeError("Native voice test must contain both audio and video")
    if (int(vids[0].get("width", 0)), int(vids[0].get("height", 0))) != (768, 1344):
        raise RuntimeError("Unexpected native H3 resolution")
    duration = float(result.get("format", {}).get("duration", 0))
    if not 4.5 < duration < 7:
        raise RuntimeError("Unexpected H3 speech-test duration")
    # A real audio stream must also be audibly nonempty. This does NOT prove
    # the words/phonemes or that lips sync: human review required.
    args = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(VIDEO), "-vn",
            "-af", "volumedetect", "-f", "null", "-"]
    r = subprocess.run(args, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError("Could not decode H3 audio")
    values = re.findall(r"mean_volume:\s*(-?[0-9.]+) dB", r.stderr)
    if not values:
        raise RuntimeError("No decoded H3 audio volume available")
    mean_db = float(values[-1])
    if not math.isfinite(mean_db) or mean_db < -65:
        raise RuntimeError(f"H3 audio is effectively silent ({mean_db} dB)")
    wav = OUTPUT / "h3-native-voix-fr.wav"
    call(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(VIDEO),
          "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
    for second in (0.5, 1.5, 2.5, 3.5, 4.5):
        file = OUTPUT / f"face-{second:.1f}s.jpg"
        call(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(second),
              "-i", str(VIDEO), "-frames:v", "1", "-q:v", "3", str(file)])
    report = {
        "output": VIDEO.name, "duration_s": duration,
        "resolution": [int(vids[0]["width"]), int(vids[0]["height"])],
        "video_codec": vids[0].get("codec_name"),
        "audio_codec": auds[0].get("codec_name"),
        "audio_mean_db": mean_db,
        "dialogue_requested": DIALOGUE,
        "technical_result": "valid H3 native audiovisual file",
        "not_automatically_verified": [
            "exact French words and pronunciation",
            "lip synchronization",
            "voice naturalness",
            "human anatomy and any face drift",
        ],
    }
    (OUTPUT / "evaluation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("H3 native French audio/video TECHNICAL PASS: " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["preflight", "render", "inspect"])
    stage = p.parse_args().stage
    {"preflight": preflight, "render": render, "inspect": inspect}[stage]()
