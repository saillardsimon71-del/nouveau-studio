import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app import media


def verify(path, folder, edit):
    info = media.probe(path).to_dict()
    assert (info["width"], info["height"], info["fps"], info["nb_frames"]) == (1080, 1920, 48, 1440), info
    assert abs(info["duration_s"] - 30) < .03
    assert info["has_audio"] and info["audio_rate"] == 48000 and info["audio_channels"] == 2
    result = subprocess.run([media.ffmpeg_bin(), "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                            capture_output=True, text=True, timeout=600)
    assert result.returncode == 0 and not result.stderr.strip(), result.stderr
    scan = subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(path),
                           "-vf", "blackdetect=d=0.12:pix_th=0.10,freezedetect=n=-60dB:d=0.5",
                           "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=600)
    assert scan.returncode == 0
    black = [{"start": float(a), "end": float(b), "duration": float(c)} for a, b, c in
             re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", scan.stderr)]
    freeze = [float(v) for v in re.findall(r"freeze_start: ([\d.]+)", scan.stderr)]
    assert not [event for event in black if event["start"] < 26.98], black
    assert not [t for t in freeze if t < 26.98], freeze
    loudness = media.loudness(path)
    assert -20 <= loudness["integrated_lufs"] <= -16
    assert loudness["true_peak_db"] <= -1
    luma = []
    frames = {}
    cuts = [s["start_frame"] for s in edit["shots"]][1:] + [1296]
    wanted = {max(0, min(1439, cut + offset)) for cut in cuts for offset in [-3, -2, -1, 0, 1, 2, 3]}
    with av.open(str(path)) as container:
        for i, frame in enumerate(container.decode(video=0)):
            im = frame.to_image()
            x = np.asarray(im.resize((96, 168)), dtype=np.float32)
            luma.append(float((x[:, :, 0] * .2126 + x[:, :, 1] * .7152 + x[:, :, 2] * .0722).mean()))
            if i in wanted:
                frames[i] = im.resize((154, 274))
    assert len(luma) == 1440
    flashes = [i for i in range(1, len(luma) - 1) if luma[i] > max(luma[i - 1], luma[i + 1]) + 24]
    assert not flashes, flashes
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
    for page, start in enumerate(range(0, len(cuts), 5)):
        sheet = Image.new("RGB", (1106, 1510), "#151715")
        draw = ImageDraw.Draw(sheet)
        for row, cut in enumerate(cuts[start:start + 5]):
            for column, offset in enumerate([-3, -2, -1, 0, 1, 2, 3]):
                i = cut + offset
                sheet.paste(frames[i], (column * 158, row * 302))
                draw.text((column * 158 + 4, row * 302 + 278), f"{i / 48:.3f}s", fill="white", font=font)
        sheet.save(folder / f"{path.stem}-cuts-{page + 1}.jpg", quality=88)
    blob = path.read_bytes()
    report = {"file": path.name, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
              "media": info, "full_decode": "pass", "decoded_frames": len(luma), "loudness": loudness,
              "detected_black_intervals": black, "detected_freeze_starts": freeze,
              "expected_static_end_card": {"start": 27, "end": 30}, "isolated_luma_spikes": flashes,
              "faststart": blob.find(b"moov") < blob.find(b"mdat"),
              "visual_review": "Frame sheets at 4 fps plus seven consecutive frames at every cut. No human real-time screening or human listening claimed."}
    assert report["faststart"]
    (folder / (path.stem + "-verification.json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path.name, "PASS", info["duration_s"], info["fps"], loudness, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--edit", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    edit = json.loads(args.edit.read_text(encoding="utf-8"))
    for source in args.sources:
        verify(source, args.output, edit)
