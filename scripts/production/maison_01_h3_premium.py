#!/usr/bin/env python3
"""MAISON / 01: fictional high-fashion portfolio film with authentic photo keyframes.

Four distinct editorials / fashion tableaux; the opening 4s is REUSED from the
already-approved Modal H3 smoke artifact (no GPU charged again).
The next three 5s H3 renders use ONE warm Modal worker, no MiniMax API.
No still-image AI generation, no uncontrolled retries, no paid stock images.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from PIL import Image, ImageOps

OUT = Path("artifacts/maison-01")
FPS = 24
SIZE = (768, 1344)
SHOT_TRIM = 4.65
HERO_TRIM = 4.20
CARD_SECONDS = 2.45
MOVIE = "MAISON-01-FASHION-FILM-H3.mp4"
MUSIC_URL = "https://www.scottbuckley.com.au/library/wp-content/uploads/2019/02/sb_ascension.mp3"
MUSIC_PAGE = "https://www.scottbuckley.com.au/library/ascension/"
CREDIT = "'Ascension' by Scott Buckley — CC BY 4.0 — www.scottbuckley.com.au"

# Real photography, individual Pexels photo detail pages and photographers verified.
SHOTS = [
    {
        "name": "runway",
        "id": 9509649,
        "photographer": "cottonbro studio",
        "page": "https://www.pexels.com/photo/a-woman-in-black-dress-walking-at-the-runway-9509649/",
        "image": "https://images.pexels.com/photos/9509649/pexels-photo-9509649.jpeg",
        "centering": (0.50, 0.45),
        "seed": 1051025,
        "prompt": (
            "Luxury editorial campaign film for an entirely fictional fashion house, "
            "based on the authentic fashion runway photo. A fashion model wears the "
            "exact same black dress and walks with measured, magnetic confidence "
            "on the same indoor runway. Keep the original face, runway architecture, "
            "garment construction and all fabric details unchanged. A refined "
            "slow tracking camera moves a short distance beside her, capturing "
            "the exquisite flow of the dress and one intense sideways glance. "
            "Runway realism: a single elegant step with plausible feet and "
            "stable hands, polished skin, true garment physics. Flash photography "
            "glints softly in the distant background, a sharp cinematic fashion cut. "
            "Stereo sound: restrained footsteps and soft shutter clicks, no dialogue. "
            "Never add more models, duplicate limbs, new shoes, logos or lettering."
        ),
    },
    {
        "name": "pearls",
        "id": 26588343,
        "photographer": "Caio Mantovani",
        "page": "https://www.pexels.com/photo/female-model-wearing-sunglasses-evening-gloves-and-pearl-necklaces-26588343/",
        "image": "https://images.pexels.com/photos/26588343/pexels-photo-26588343.jpeg",
        "centering": (0.50, 0.45),
        "seed": 1051026,
        "prompt": (
            "A prestige haute-couture editorial campaign. The original REAL black "
            "and white studio photograph shows an elegant adult female model "
            "wearing the exact same evening gloves, sunglasses and layered pearls. "
            "Preserve the precise face, pearl placement, glove shape, makeup, "
            "silhouette and monochrome palette. With controlled slow-motion she "
            "moves a gloved hand only a few centimeters toward her collarbone, "
            "then gives the camera a provocative, unwavering gaze. Extremely "
            "close fashion-film camera drift, sumptuous satin and pearl "
            "specular reflections, high-contrast silver-gelatin texture and "
            "subtle optical highlights. Fingers and pearls remain anatomically "
            "real and stationary relative to their attachments. "
            "Audio: tactile satin rustle, subtle pearls touching, room tone. "
            "No additional fingers, no floating jewelry, no wardrobe edits, "
            "no text or fashion label, no cuts in this shot."
        ),
    },
    {
        "name": "tuxedo",
        "id": 30042492,
        "photographer": "Arian Fernandez",
        "page": "https://www.pexels.com/photo/elegant-man-in-tuxedo-with-stylish-sunglasses-30042492/",
        "image": "https://images.pexels.com/photos/30042492/pexels-photo-30042492.jpeg",
        "centering": (0.50, 0.45),
        "seed": 1051027,
        "prompt": (
            "Fashion-film finale from a TRUE black-and-white Pexels editorial "
            "portrait of an adult male model in a tuxedo and sunglasses. "
            "Preserve his exact identity, glasses, lapel details, white shirt "
            "and studio backdrop; keep original monochrome photography. "
            "A deliberate subtle interaction: model turns his face a few "
            "degrees toward camera, brushes the tuxedo lapel ONCE with "
            "an anatomically plausible hand, and finishes in a commanding "
            "still pose. Cinematic lateral camera slide with a controlled "
            "high-fashion strobe flash, rich blacks, precise silver-white "
            "highlights, glamorous tailored fabric details, luxury magazine "
            "film aesthetic. Original expression confident and poised, "
            "no warping glasses, no mutated fingers, no additional person, "
            "no extra accessories, no brand, no captions. "
            "Audio: subdued camera shutter and rustle of tuxedo fabric."
        ),
    },
]


def run(args: list[str]) -> str:
    p = subprocess.run(args, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError("Command failed: " + " ".join(args[:4]) + "\n" + p.stderr[-3500:])
    return p.stdout.strip()


def fetch(url: str, maximum: int = 24_000_000) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SiteQuiVend-Portfolio-H3"})
    with urllib.request.urlopen(request, timeout=80) as response:
        data = response.read(maximum + 1)
    if len(data) < 20_000 or len(data) > maximum:
        raise ValueError(f"Unexpected download size {len(data)} for {url}")
    return data


def preflight() -> None:
    refs = OUT / "references"
    refs.mkdir(parents=True, exist_ok=True)
    records = []
    for shot in SHOTS:
        original = refs / f"{shot['name']}-original.jpg"
        png = refs / f"{shot['name']}-real-firstframe.png"
        if not original.exists():
            original.write_bytes(fetch(shot["image"]))
        raw = original.read_bytes()
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        if min(im.size) < 720:
            raise ValueError(f"Insufficient authentic photo resolution for {shot['name']}: {im.size}")
        ref = ImageOps.fit(im, SIZE, centering=shot["centering"], method=Image.Resampling.LANCZOS)
        ref.save(png, optimize=True)
        if png.stat().st_size > 24 * 1024 * 1024:
            raise ValueError("Prepared photographic PNG exceeds H3 limit")
        records.append({
            "shot": shot["name"], "photo_id": shot["id"], "photographer": shot["photographer"],
            "photo_page": shot["page"], "download": shot["image"],
            "original_sha256": hashlib.sha256(raw).hexdigest(),
            "firstframe_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
            "original_dimensions": list(im.size), "prepared_dimensions": list(SIZE),
        })
    music = OUT / "music" / "ascension-scott-buckley.mp3"
    music.parent.mkdir(parents=True, exist_ok=True)
    if not music.exists():
        music.write_bytes(fetch(MUSIC_URL, maximum=25_000_000))
    audio = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(music)]))
    if not any(s.get("codec_type") == "audio" for s in audio["streams"]):
        raise ValueError("No valid licensed soundtrack")
    (OUT / "sources.json").write_text(json.dumps({
        "concept": "Fictional luxury maison; independent unpaid concept, no affiliation/endorsement",
        "input_image_policy": "Real Pexels photographs ONLY; no AI-generated stills",
        "photos": records, "license": "https://www.pexels.com/license/",
        "music": {"url": MUSIC_PAGE, "credit": CREDIT, "license": "CC BY 4.0"},
        "reuse": "Approved H3 smoke shot from GitHub Actions run 40186176902 artifact 12596460909"
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PREFLIGHT PASS — authentic Pexels photos + music, no GPU and no generated images", flush=True)


def render() -> None:
    import modal
    samples = []
    for shot in SHOTS:
        path = OUT / "references" / f"{shot['name']}-real-firstframe.png"
        if not path.is_file():
            raise FileNotFoundError("Missing original real photograph: " + str(path))
        samples.append({
            "prompt": shot["prompt"], "duration_s": 5.0, "aspect_ratio": "9:16",
            "seed": shot["seed"], "steps": 20, "audio_mode": "native",
            "image_png_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        })
    print("ONE Modal GPU batch for 3 distinct H3 scenes, 20 steps each; no automatic retries", flush=True)
    started = time.monotonic()
    func = modal.Function.from_name("pvs-minimax-h3", "render_batch", environment_name="main").hydrate()
    result = func.remote(samples)
    rendered = result.get("shots", [])
    if len(rendered) != len(SHOTS):
        raise RuntimeError("H3 batch returned fewer scenes than requested; do not assemble")
    clips = OUT / "clips"
    clips.mkdir(exist_ok=True)
    report = []
    for item, scene in zip(rendered, SHOTS):
        video = clips / (scene["name"] + "-h3.mp4")
        raw = base64.b64decode(item["video_base64"], validate=True)
        if not 30_000 < len(raw) < 25 * 1024 * 1024:
            raise RuntimeError("H3 produced invalid/oversized MP4 for " + scene["name"])
        video.write_bytes(raw)
        report.append({**item["metadata"], "name": scene["name"],
                       "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        print("SAVED " + str(video) + " BYTES=" + str(len(raw)), flush=True)
    (OUT / "render-report.json").write_text(json.dumps({
        "batch_wall_s": result.get("batch_wall_seconds"),
        "github_including_transfer_wall_s": round(time.monotonic() - started, 2),
        "shots": report,
    }, indent=2), encoding="utf-8")


def media(path: Path) -> dict:
    d = json.loads(run(["ffprobe", "-v", "error", "-show_format",
                        "-show_streams", "-of", "json", str(path)]))
    if not any(s.get("codec_type") == "video" for s in d.get("streams", [])):
        raise ValueError("MP4 has no video: " + str(path))
    return d


def prepare_clip(src: Path, dst: Path, seconds: float) -> None:
    info = media(src)
    video = next(s for s in info["streams"] if s.get("codec_type") == "video")
    if int(video.get("width", 0)) < 700 or int(video.get("height", 0)) < 1300:
        raise ValueError(f"Unexpected source geometry: {src} {video}")
    if float(info["format"]["duration"]) + 0.06 < seconds:
        raise ValueError(f"Scene too short to trim: {src}")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-t", str(seconds),
         "-vf", "fps=24,scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,setsar=1,format=yuv420p",
         "-an", "-r", "24", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)])


def assemble() -> None:
    hero = OUT / "hero-cache" / "MAISON-01-H3-SMOKE-4s.mp4"
    if not hero.is_file():
        raise FileNotFoundError("Approved hero H3 MP4 missing from prior artifact; refusing replacement")
    prepared = OUT / "prepared"
    exports = OUT / "exports"
    prepared.mkdir(exist_ok=True)
    exports.mkdir(exist_ok=True)
    paths = []
    for name, src, trim in [("hero", hero, HERO_TRIM)] + [
            (s["name"], OUT / "clips" / (s["name"] + "-h3.mp4"), SHOT_TRIM) for s in SHOTS]:
        if not src.is_file() or src.stat().st_size < 30_000:
            raise FileNotFoundError("Missing authentic H3 video: " + str(src))
        processed = prepared / (name + "-24fps.mp4")
        prepare_clip(src, processed, trim)
        paths.append(processed)
    font_serif = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    font_sans = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not Path(font_serif).exists():
        raise FileNotFoundError("Endcard serif font not installed")
    card = prepared / "endcard.mp4"
    filt = (
        f"drawtext=fontfile={font_serif}:text='MAISON / 01':fontcolor=0xE8E1D4:"
        "fontsize=84:x=(w-text_w)/2:y=802,"
        "drawbox=x=290:y=930:w=500:h=2:color=0xBFA98A@0.8:t=fill,"
        f"drawtext=fontfile={font_sans}:text='A STUDY IN MOTION':"
        "fontcolor=0xBFA98A:fontsize=28:x=(w-text_w)/2:y=996,"
        f"drawtext=fontfile={font_sans}:text='CONCEPT FILM - SITEQUIVEND.FR':"
        "fontcolor=0xC5C5C5:fontsize=24:x=(w-text_w)/2:y=1130,"
        "format=yuv420p"
    )
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=0x0A0A0D:s=1080x1920:r=24:d={CARD_SECONDS}",
         "-vf", filt, "-t", str(CARD_SECONDS),
         "-an", "-c:v", "libx264", "-preset", "slow",
         "-crf", "17", "-pix_fmt", "yuv420p", str(card)])
    paths.append(card)
    listing = prepared / "concat.txt"
    listing.write_text("".join("file '"+str(p.resolve())+"'\n" for p in paths), encoding="utf-8")
    picture = prepared / "picture.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-an", "-c", "copy", str(picture)])
    length = HERO_TRIM + len(SHOTS) * SHOT_TRIM + CARD_SECONDS
    music = OUT / "music" / "ascension-scott-buckley.mp3"
    if not music.is_file():
        raise FileNotFoundError("Licensed soundtrack is required")
    final = exports / MOVIE
    fade_out = length - 1.25
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(picture), "-ss", "42", "-i", str(music),
         "-filter_complex",
         f"[1:a]atrim=0:{length},asetpts=PTS-STARTPTS,volume=-3dB,"
         f"afade=t=in:st=0:d=0.35,afade=t=out:st={fade_out}:d=1.25,"
         f"apad=whole_dur={length},atrim=0:{length}[score]",
         "-map", "0:v", "-map", "[score]", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-t", str(length), "-movflags", "+faststart", str(final)])
    info = media(final)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    if not any(s["codec_type"] == "audio" for s in info["streams"]):
        raise ValueError("Final movie missing licensed soundtrack")
    if (int(v["width"]), int(v["height"])) != (1080, 1920):
        raise ValueError("Incorrect final geometry")
    measured = float(info["format"]["duration"])
    if not length - .12 <= measured <= length + .18:
        raise ValueError(f"Final duration unexpectedly {measured} vs {length}")
    poster = exports / "MAISON-01-cover.jpg"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", "2.3", "-i", str(final), "-frames:v", "1", str(poster)])
    web = exports / "MAISON-01-site-720p.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(final), "-vf", "scale=720:1280:flags=lanczos",
         "-c:v", "libx264", "-preset", "fast", "-crf", "24",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(web)])
    credits = ("MAISON / 01 — fictional SiteQuiVend concept fashion film; NOT a commissioned client ad.\n"
               "Opening keyframe and video: Anand Kulkarni — https://www.pexels.com/photo/studio-shot-of-a-woman-in-a-black-suit-and-sunglasses-22856115/\n"
               + "\n".join(f"{s['photographer']} — {s['page']}" for s in SHOTS) + "\n"
               + "Pexels license: https://www.pexels.com/license/\n"
               + "Music: " + CREDIT + "\n")
    (exports / "CREDITS.txt").write_text(credits, encoding="utf-8")
    delivery = {
        "kind": "fictional_not_commissioned",
        "name": MOVIE, "duration": measured,
        "full_hd_upscale": "1080x1920 (H3 original images are 768x1344)",
        "fps": 24, "source_shots": [p.name for p in paths],
        "music": MUSIC_PAGE, "music_credit": CREDIT,
        "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
        "review": "NOT AUTOMATICALLY APPROVED: inspect all frames, hands, garments, transitions, audio and typography.",
        "publish": "Do not update SiteQuiVend production until manually approved."
    }
    (exports / "delivery.json").write_text(json.dumps(delivery, indent=2), encoding="utf-8")
    print(f"RENDERED REAL FINAL {final} {measured:.2f}s, cover, web MP4, credits", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "render", "assemble"])
    phase = parser.parse_args().phase
    if phase == "prepare":
        preflight()
    elif phase == "render":
        render()
    else:
        assemble()
