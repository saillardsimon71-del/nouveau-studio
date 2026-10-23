import argparse
import json
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def review(source, folder, sample_fps=4):
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    changes = []
    previous = None
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate)
        for i, frame in enumerate(container.decode(stream)):
            small = frame.to_image().resize((96, 168))
            x = np.asarray(small, dtype=np.float32)
            if previous is not None:
                changes.append(float(np.abs(x - previous).mean()))
            previous = x
            if i % round(fps / sample_fps) == 0:
                frames.append((i / fps, frame.to_image()))
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
    for page, start in enumerate(range(0, len(frames), 24)):
        selected = frames[start:start + 24]
        sheet = Image.new("RGB", (1440, 1800), "#131513")
        draw = ImageDraw.Draw(sheet)
        for j, (t, im) in enumerate(selected):
            x, y = (j % 6) * 240, (j // 6) * 450
            sheet.paste(im.resize((234, 416)), (x, y))
            draw.text((x + 8, y + 420), f"{t:.2f}s", font=font, fill="white")
        sheet.save(folder / f"{source.stem}-{page + 1}.jpg", quality=90)
    metrics = {"source": str(source), "sample_fps": sample_fps, "sampled_frames": len(frames),
               "consecutive_frame_mae": changes, "minimum_mae": min(changes),
               "note": "Frame sampling supports visual review; motion metrics alone do not judge the product action or aesthetics."}
    (folder / f"{source.stem}-motion.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(source.stem, len(frames), "review frames", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for source in args.sources:
        review(source, args.output)
