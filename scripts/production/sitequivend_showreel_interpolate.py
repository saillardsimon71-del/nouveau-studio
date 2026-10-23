import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import av
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app import media


def interpolate(source, rife):
    output = source.with_name(source.stem + "-48.mp4")
    metadata = output.with_suffix(".json")
    if output.exists() and metadata.exists():
        print("REUSE", output.name, flush=True)
        return
    started = time.monotonic()
    frames = source.parent / (source.stem + "-frames")
    middle = source.parent / (source.stem + "-rife")
    frames.mkdir(exist_ok=True)
    middle.mkdir(exist_ok=True)
    media.run_ffmpeg(["-i", str(source), "-map", "0:v", "-fps_mode", "passthrough", str(frames / "%08d.png")])
    count = len(list(frames.glob("*.png")))
    target = count * 2 - 1
    print("RIFE", source.name, count, "->", target, flush=True)
    result = subprocess.run([str(rife / "rife-ncnn-vulkan.exe"), "-i", str(frames), "-o", str(middle),
                             "-n", str(target), "-m", str(rife / "rife-v4.6"), "-g", "0", "-j", "1:1:2"],
                            capture_output=True, text=True, timeout=600)
    (source.parent / (source.stem + "-rife.log")).write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    assert len(list(middle.glob("*.png"))) == target
    differences = []
    for index in range(2, target, 2):
        a = np.asarray(Image.open(frames / f"{index // 2:08d}.png"), dtype=np.float32)
        b = np.asarray(Image.open(frames / f"{index // 2 + 1:08d}.png"), dtype=np.float32)
        m = np.asarray(Image.open(middle / f"{index:08d}.png"), dtype=np.float32)
        differences.append([float(np.abs(m - a).mean()), float(np.abs(m - b).mean())])
    media.run_ffmpeg(["-framerate", "48", "-i", str(middle / "%08d.png"), "-c:v", "libx264",
                      "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", str(output)])
    with av.open(str(output)) as container:
        stream = container.streams.video[0]
        assert float(stream.average_rate) == 48 and stream.frames == target
    report = {"method": "RIFE 4.6 ncnn Vulkan, within source take only", "input_fps": 24, "output_fps": 48,
              "input_frames": count, "output_frames": target, "computed_intermediates": len(differences),
              "intermediates_different_from_both_neighbors": sum(min(pair) > .01 for pair in differences),
              "intermediate_mae_to_neighbors": differences, "seconds": round(time.monotonic() - started, 2)}
    metadata.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("DONE", output.name, report["seconds"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--rife", required=True, type=Path)
    args = parser.parse_args()
    for source in args.sources:
        interpolate(source.resolve(), args.rife.resolve())
