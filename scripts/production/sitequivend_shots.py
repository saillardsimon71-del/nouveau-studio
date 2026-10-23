import argparse
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("PVS_MODAL_APP", "pvs-sitequivend-ad")
os.environ.setdefault("PVS_MODAL_RENDER_TIMEOUT", "900")
from deploy import modal_ltx_worker as worker


PROMPTS = {
    "produit": "A continuous luxury perfume commercial. Preserve exactly the unbranded amber glass bottle and bronze cap from the reference, perfectly stable glass geometry, closed cap, blank front with no label or lettering. A smooth controlled camera arc of six degrees with a gentle slow push-in reveals moving specular highlights and amber caustics through thick glass. Water glistens on charcoal basalt, a few droplets slide naturally, very subtle mist moves behind the bottle. The bottle remains upright and completely unchanged. Rich warm copper backlight, precise optical reflections, detailed real glass and dark stone, expensive studio product cinematography, no camera shake, no cuts, no transformation of the object, no text, no logo, no people. Sound of a few delicate water drops, no speech and no music.",
    "restaurant": "A continuous photorealistic fine dining commercial. Preserve exactly the plated chocolate dessert, ivory ceramic plate, raspberries and curved chocolate shard from the reference. A refined slow macro dolly move travels a few centimeters sideways while gently pushing toward the chocolate, believable optical parallax and shallow depth of field. A faint wisp of steam rises and chocolate highlights move naturally; the dessert does not change shape and the molten center barely settles. Warm candle bokeh softly flickers in the dark restaurant background. Appetizing cocoa texture and realistic glossy chocolate, luxury cinematic food photography, no hands, no people, no added food, no utensils appearing, no text, no logos, no cuts, no camera shake. Very quiet restaurant room tone, no dialogue, no music.",
    "villa": "A continuous photorealistic luxury real estate commercial. Preserve exactly the contemporary travertine villa and all straight columns, window frames, flat roof, terrace, olive tree and rectangular pool from the reference. A calm smooth camera dolly moves forward half a meter and slightly to the right, creating subtle real parallax. Gentle water ripples carry the warm interior reflections across the pool; olive leaves move a little in a light breeze. The building is structurally stable, every wall, door and window stays rigid and in place. Elegant early blue hour, soft copper sunset and inviting warm ivory interior lights, real architectural photography, restrained cinematic contrast, no people, no vehicles, no text, no logo, no cut, no surreal geometry. Gentle pool water and evening breeze, no music and no speech.",
    "interieur": "Transform this exact source-video living room into a photorealistic premium architectural advertisement at golden hour. Preserve the source camera trajectory, exact room layout, number and placement of chairs, low rectangular slatted timber coffee table, television wall, large left glass windows, ceiling lines and floor geometry. Keep all structural lines straight and do not add doors, windows, objects or people. Replace flat daylight with rich warm copper sunset light streaming through the same windows, elegant golden shafts of light and natural soft shadows. Sophisticated material finish with warm ivory upholstery, detailed natural wood and pale warm stone, vivid lush green foliage outside the windows. High-end real estate cinematography, restrained warm film grade, realistic exposure and coherent physically accurate reflections, stable furniture throughout the moving shot. No cartoon rendering, no text, no signs, no logos. Very quiet interior room tone, no music and no dialogue.",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--shots", nargs="+", choices=list(PROMPTS), default=list(PROMPTS))
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    (args.work / "video-prompts.json").write_text(json.dumps(PROMPTS, indent=2), encoding="utf-8")
    with worker.app.run():
        for index, name in enumerate(args.shots):
            out = args.work / f"{name}-ltx.mp4"
            meta = out.with_suffix(".json")
            if out.exists() and meta.exists() and json.loads(meta.read_text())["bytes"] == out.stat().st_size:
                print(f"REUSE {name}: {out}", flush=True)
                continue
            payload = {"prompt": PROMPTS[name], "duration_s": 5, "aspect_ratio": "9:16",
                       "audio_mode": "native", "image_strength": 0.85, "seed": 812310 + list(PROMPTS).index(name),
                       "trace_id": f"sqv-{name}-v1"}
            if name == "interieur":
                source = args.work / "source-interieur-5s.mp4"
                payload["video_mp4_base64"] = base64.b64encode(source.read_bytes()).decode()
                worker.probe_source_video(source, worker.validate(payload))
            else:
                payload["image_png_base64"] = base64.b64encode((args.work / f"{name}-reference.png").read_bytes()).decode()
            print(f"RENDER {name}, 121 frames, L40S, no automatic retry", flush=True)
            result = worker.render_clip.remote(payload)
            out.write_bytes(base64.b64decode(result["video_base64"]))
            metadata = result["metadata"]
            metadata["prompt"] = PROMPTS[name]
            metadata["cost_estimate_usd"] = worker.estimate_cost_usd("L40S", metadata["generation_seconds"])
            meta.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"DONE {name}: {metadata['generation_seconds']} seconds, {out.stat().st_size} bytes", flush=True)


if __name__ == "__main__":
    main()
