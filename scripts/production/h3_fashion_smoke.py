"""One controlled, billable Modal GPU smoke render from an authentic Pexels photo.

This is an engineering validation, not a portfolio-ready client spot.
No image generation, no MiniMax paid API. One Modal call only, no retries.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import urllib.request

from PIL import Image, ImageOps

SOURCE = {
    "photo_url": "https://www.pexels.com/photo/studio-shot-of-a-woman-in-a-black-suit-and-sunglasses-22856115/",
    "jpeg": "https://images.pexels.com/photos/22856115/pexels-photo-22856115.jpeg",
    "photographer": "Anand Kulkarni",
    "license": "https://www.pexels.com/license/",
}
OUT = Path("artifacts/h3-fashion-smoke")
PROMPT = (
    "A film for a completely fictional high-fashion house, based exclusively on "
    "the original real editorial photograph: an adult woman wearing a precisely "
    "tailored black suit and sunglasses. Maintain her exact face, hairstyle, "
    "sunglasses, jacket cut and studio background throughout. A graceful "
    "slow-motion pose: she deliberately adjusts her blazer lapel with one hand "
    "then turns her head slightly and meets the camera with a poised, "
    "self-assured gaze. Slow close cinematic push-in, sophisticated chiaroscuro "
    "lighting, rich fabric microtexture, soft luminous accents, subtle shutter "
    "flare. One unbroken shot; photorealistic realistic hands and anatomy. "
    "Audio: delicate couture editorial ambience and one restrained cloth rustle. "
    "No logos, no text, no outfit changes, no morphing, no added people."
)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(SOURCE["jpeg"], headers={"User-Agent": "Mozilla/5.0 SiteQuiVend-H3/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read(20_000_001)
    if not 20_000 < len(raw) < 20_000_000:
        raise RuntimeError("Invalid image download size")
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    if min(img.size) < 700:
        raise RuntimeError("Original Pexels photo has inadequate resolution")
    ref = ImageOps.fit(img, (768, 1344), method=Image.Resampling.LANCZOS)
    path = OUT / "source-pexels.png"
    ref.save(path, optimize=True)
    proof = {**SOURCE, "original_sha256": hashlib.sha256(raw).hexdigest(),
             "reference_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
             "reference_px": [768, 1344], "model": "MiniMax-H3 FL2VA", "gpu": "Modal L40S"}
    (OUT / "provenance.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print("Pexels authentic image prepared. Starting one Modal H3 GPU render", flush=True)

    import modal
    func = modal.Function.from_name("pvs-minimax-h3", "render_clip", environment_name="main").hydrate()
    result = func.remote({
        "prompt": PROMPT, "duration_s": 4, "aspect_ratio": "9:16", "seed": 20261025,
        "steps": 20, "audio_mode": "native",
        "image_png_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
    })
    data = base64.b64decode(result["video_base64"], validate=True)
    video = OUT / "MAISON-01-H3-SMOKE-4s.mp4"
    if len(data) < 20_000:
        raise RuntimeError("Output too small to be a real MP4")
    video.write_bytes(data)
    meta = result.get("metadata", {})
    (OUT / "result.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("REAL_MP4="+str(video)+" BYTES="+str(video.stat().st_size), flush=True)


if __name__ == "__main__":
    main()
