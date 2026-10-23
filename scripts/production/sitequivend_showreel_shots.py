import argparse
import base64
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
MANIFEST = json.loads(Path(__file__).with_name("sitequivend_showreel.json").read_text(encoding="utf-8"))
os.environ["PVS_MODAL_APP"] = MANIFEST["modal_app"]
os.environ["PVS_MODAL_RENDER_TIMEOUT"] = "700"
from deploy import modal_ltx_worker as worker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--shots", nargs="+", default=[s["id"] for s in MANIFEST["shots"]])
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    selected = [s for s in MANIFEST["shots"] if s["id"] in args.shots]
    assert len(selected) == len(args.shots), "Unknown or duplicate shot"
    for shot in selected:
        image = Image.open(args.work / "references" / f"{shot['pexels_id']}.jpg").convert("RGB")
        box = tuple(round(v * (image.width if i % 2 == 0 else image.height)) for i, v in enumerate(shot["crop"]))
        image = ImageOps.fit(image.crop(box), (768, 1344), method=Image.Resampling.LANCZOS)
        image.save(args.work / f"{shot['id']}-reference.png")
    if args.prepare_only:
        return
    with worker.app.run():
        for shot in selected:
            dest = args.work / f"{shot['id']}-ltx.mp4"
            meta = dest.with_suffix(".json")
            if dest.exists() and meta.exists():
                assert dest.stat().st_size == json.loads(meta.read_text())["bytes"]
                print("REUSE", shot["id"], flush=True)
                continue
            spent = sum(json.loads(p.read_text())["cost_estimate_usd"] for p in args.work.glob("*-ltx.json"))
            if spent > MANIFEST["generation_estimate_limit_usd"] - .2:
                raise RuntimeError("Production estimate limit reached; inspect billing before continuing")
            payload = {"prompt": shot["prompt"], "duration_s": shot["duration_s"], "aspect_ratio": "9:16",
                       "audio_mode": "native", "image_strength": .88, "seed": shot["seed"],
                       "trace_id": "sqv-portfolio-" + shot["id"],
                       "image_png_base64": base64.b64encode((args.work / f"{shot['id']}-reference.png").read_bytes()).decode()}
            worker.validate(payload)
            print("RENDER", shot["id"], "no automatic retry", flush=True)
            result = worker.render_clip.remote(payload)
            dest.write_bytes(base64.b64decode(result["video_base64"]))
            metadata = result["metadata"]
            metadata.update(prompt=shot["prompt"], pexels_source=shot["source"], action=shot["action"],
                            cost_estimate_usd=worker.estimate_cost_usd("L40S", metadata["generation_seconds"]))
            meta.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            print("DONE", shot["id"], metadata["generation_seconds"], "seconds", flush=True)


if __name__ == "__main__":
    main()
