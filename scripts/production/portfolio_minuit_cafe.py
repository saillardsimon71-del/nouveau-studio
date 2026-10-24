#!/usr/bin/env python3
"""SiteQuiVend showreel: three original Pexels photographs -> LTX shots -> 48fps cut.
No GPU use by this script; render happens ONLY in manual GitHub Actions steps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

ASSETS = [
    {
        "name": "beans",
        "sector": "coffee",
        "pexels_id": 36722820,
        "photographer": "Marcus Echo",
        "page": "https://www.pexels.com/photo/close-up-of-roasted-coffee-beans-on-dark-background-36722820/",
        "download": "https://images.pexels.com/photos/36722820/pexels-photo-36722820.jpeg",
        "description": "Real roasted coffee beans in low key lighting"
    },
    {
        "name": "extraction",
        "sector": "coffee",
        "pexels_id": 30818517,
        "photographer": "James Collington",
        "page": "https://www.pexels.com/photo/close-up-of-espresso-pouring-from-coffee-machine-30818517/",
        "download": "https://images.pexels.com/photos/30818517/pexels-photo-30818517.jpeg",
        "description": "Real espresso flowing into a clear cup"
    },
    {
        "name": "cup",
        "sector": "coffee",
        "pexels_id": 20884081,
        "photographer": "Alex Souza",
        "page": "https://www.pexels.com/photo/cup-of-espresso-on-a-saucer-20884081/",
        "download": "https://images.pexels.com/photos/20884081/pexels-photo-20884081.jpeg",
        "description": "Finished espresso in a cup in dark studio light"
    }
]

MUSIC_URL = "https://www.scottbuckley.com.au/library/wp-content/uploads/2019/02/sb_ascension.mp3"
MUSIC_PAGE = "https://www.scottbuckley.com.au/library/ascension/"
MUSIC_CREDIT = "'Ascension' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au"
FPS = 48
SHOT_LENGTH = 4.0
END_LENGTH = 3.0
OUT_NAME = "MINUIT-CAFE-Spot-15s-LTX.mp4"


def call(args: list[str]) -> str:
    p = subprocess.run(args, check=True, capture_output=True, text=True)
    return p.stdout.strip()


def download(url: str, path: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 Portfolio-Minuit/1.0 (portfolio asset download)"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(32_000_001)
        if len(data) > 32_000_000:
            raise ValueError("Source image/audio unexpectedly larger than 32MB")
    if len(data) < 20_000:
        raise ValueError(f"Downloaded source is unexpectedly short: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def check_media(path: Path, *, codec: str | None = None) -> dict:
    info = json.loads(call([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size:stream=codec_name,width,height,r_frame_rate",
        "-of", "json", str(path)
    ]))
    streams = info.get("streams") or []
    if codec is not None and not any(s.get("codec_name") == codec for s in streams):
        raise ValueError(f"{path}: expected {codec}; got {streams}")
    return info


def prepare(out: Path) -> None:
    """Downloads only THREE hand-selected photos; validates images and licensed music pre-GPU."""
    from PIL import UnidentifiedImageError
    (out / "references").mkdir(parents=True, exist_ok=True)
    source_info = []
    for shot in ASSETS:
        raw = out / "references" / (shot["name"] + "-pexels.jpg")
        png = out / "references" / (shot["name"] + "-reference.png")
        if not raw.exists():
            download(shot["download"], raw)
        try:
            with Image.open(raw) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                if min(im.size) < 600:
                    raise ValueError(f"{shot['name']} too low resolution: {im.size}")
                # Input LTX grid: 768x1344. No color manipulation or AI illustration.
                im = ImageOps.fit(im, (768, 1344), method=Image.Resampling.LANCZOS,
                                  centering=(0.50, 0.48))
                im.save(png, optimize=True)
        except (UnidentifiedImageError, OSError) as e:
            raise ValueError(f"Pexels source not a readable image: {shot['page']}") from e
        source_info.append({
            "name": shot["name"],
            "photographer": shot["photographer"],
            "original_page": shot["page"],
            "source_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
            "image_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
            "width": 768, "height": 1344,
        })
    track = out / "music" / "ascension-scott-buckley.mp3"
    if not track.exists():
        download(MUSIC_URL, track)
    check_media(track, codec="mp3")
    (out / "source-provenance.json").write_text(json.dumps({
        "photos": source_info,
        "license": "https://www.pexels.com/license/",
        "license_notes": "Pexels images used in a transformed creative work; no affiliation or endorsement from photographers/brands implied.",
        "music": {"url": MUSIC_PAGE, "credit": MUSIC_CREDIT, "license": "CC BY 4.0"}
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("PREFLIGHT OK — 3 Pexels images and original licensed music validated, 0 GPU calls")


def prepare_clip(src: Path, dest: Path) -> None:
    check_media(src, codec="h264")
    # Motion-interpolate native 24fps LTX to 48fps BEFORE upscaling, not frame duplication.
    call([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", "0.4", "-i", str(src), "-t", str(SHOT_LENGTH),
        "-vf", (
            "minterpolate=fps=48:mi_mode=mci:mc_mode=obmc:me_mode=bidir:vsbmc=1,"
            "scale=1080:1920:flags=lanczos,setsar=1,format=yuv420p"
        ),
        "-an", "-r", "48", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-profile:v", "high", "-pix_fmt", "yuv420p", str(dest),
    ])


def assemble(out: Path) -> None:
    """Real LTX clips only. Hard cuts, restrained branded endcard, licensed score."""
    clips = out / "clips"
    export = out / "exports"
    export.mkdir(parents=True, exist_ok=True)
    prepared = out / "prepared"
    prepared.mkdir(parents=True, exist_ok=True)
    names = []
    for shot in ASSETS:
        src = clips / f"{shot['name']}-ltx.mp4"
        if not src.exists() or src.stat().st_size < 50_000:
            raise FileNotFoundError(f"Missing real LTX MP4: {src}; no static-photo substitutes allowed")
        dest = prepared / f"{shot['name']}-48fps.mp4"
        prepare_clip(src, dest)
        names.append(dest)
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    end = prepared / "endcard-48fps.mp4"
    call([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=0x0b0d10:s=1080x1920:r=48:d={END_LENGTH}",
        "-vf", (
            f"drawtext=fontfile={font}:text='MINUIT':fontcolor=white:fontsize=106:"
            "x=(w-text_w)/2:y=790,"
            f"drawtext=fontfile={font}:text='LE CAFE, AUTREMENT':fontcolor=0xC4A77A:"
            "fontsize=36:x=(w-text_w)/2:y=940,"
            f"drawtext=fontfile={font}:text='CONCEPT - SITEQUIVEND.FR':fontcolor=white:"
            "fontsize=31:x=(w-text_w)/2:y=1050,format=yuv420p"
        ),
        "-t", str(END_LENGTH), "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p", str(end)
    ])
    names.append(end)
    concat_list = prepared / "concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in names), encoding="utf-8")
    picture = prepared / "picture.mp4"
    call([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
        "-safe", "0", "-i", str(concat_list), "-an", "-c", "copy", str(picture)
    ])
    soundtrack = out / "music" / "ascension-scott-buckley.mp3"
    if not soundtrack.exists():
        raise FileNotFoundError("Licensed soundtrack missing: preflight must run successfully")
    target = export / OUT_NAME
    duration = len(ASSETS) * SHOT_LENGTH + END_LENGTH
    call([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(picture), "-ss", "46", "-i", str(soundtrack),
        "-filter_complex", (
            f"[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS,"
            f"volume=-5dB,afade=t=in:st=0:d=0.25,afade=t=out:st={duration-0.9}:d=0.9,"
            f"apad=whole_dur={duration},atrim=0:{duration}[music]"
        ),
        "-map", "0:v", "-map", "[music]", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", str(duration),
        "-movflags", "+faststart", str(target)
    ])
    probe = check_media(target, codec="h264")
    video = next(s for s in probe["streams"] if s.get("codec_name") == "h264")
    if video.get("r_frame_rate") != "48/1":
        raise ValueError(f"Invalid final fps: {video}")
    if (video.get("width"), video.get("height")) != (1080, 1920):
        raise ValueError(f"Invalid final dimensions: {video}")
    measured = float(probe["format"]["duration"])
    if not 14.5 <= measured <= 15.5:
        raise ValueError(f"Final video has unexpected duration: {measured}s")
    cover = export / "MINUIT-CAFE-cover.jpg"
    call(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "1.2",
          "-i", str(target), "-frames:v", "1", str(cover)])
    manifest = {
        "video": target.name,
        "duration_s": measured, "fps": 48, "size": "1080x1920",
        "sources": [shot["page"] for shot in ASSETS],
        "music_credit": MUSIC_CREDIT,
        "video_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "quality_disclaimer": "48fps interpolation needs visual review for motion artifacts; not native 48fps LTX.",
        "note": "Fictional coffee brand portfolio demonstration. Not a real client commission or product endorsement."
    }
    (export / "delivery.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (export / "CREDITS.txt").write_text(
        "MINUIT CAFE: fictional concept ad produced by SiteQuiVend. Photography licensed from Pexels:\n" +
        "\n".join(f"{a['photographer']} — {a['page']}" for a in ASSETS) +
        "\nMusic: " + MUSIC_CREDIT + "\n", encoding="utf-8"
    )
    print(f"DELIVERED: {target} {measured:.2f}s @48fps — inspect every cut before publication")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "assemble"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.out)
        else:
            assemble(args.out)
    except Exception as exc:
        print(f"FAILED — {exc}", file=sys.stderr)
        raise

# Production request: one one-time GitHub Actions render, 3 Modal calls, no automatic retry.
