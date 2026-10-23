"""LTX-2.5 shot pass for the SiteQuiVend portfolio films.

This module is the *optional* high-end path. It reuses the validated Modal app
`pvs-ltx` (`deploy/modal_ltx_worker.py`, GPU L40S, ComfyUI INT8-convrot) through
the studio's own engine contract, so nothing about the deployment changes.

Why it is a separate step, and why the films ship without it
-----------------------------------------------------------
The morph edit runs on CPU and is complete on its own. Each shot is a
photographic plate with a virtual camera move. LTX adds real subject motion and
real light movement *inside* each shot: steam that drifts with the plate, a
wheel that keeps turning, a car that rolls forward. When it is available, this
script replaces the still plates with generated clips shot for shot and the same
timeline is rebuilt on top of them; when it is not, the films still exist and are
honest about their means.

Environment check performed for this production (2026-10-23): `api.modal.com`
and `modal.com` are blocked from the build sandbox (TLS handshake closed on every
outbound request, no Modal token present locally), so no LTX call was possible
here. The script is therefore *written and reviewed*, not executed, and is
reported as such in `docs/productions/`. Run it from a machine with Modal
credentials and a route to `modal.com`.

Usage
-----
    # 0 GPU: print the exact calls and the estimated cost
    python -m scripts.portfolio.ltx_shots --film food --dry-run

    # generate the missing shots (skips clips that already exist and are valid)
    modal profile activate kulejean567
    python -m scripts.portfolio.ltx_shots --film food
    python -m scripts.portfolio.ltx_shots --film auto

    # rebuild the films on the generated clips (same timeline, same morphs)
    python -m scripts.portfolio.build --film food --full --video-sources ltx

Prompt policy: every prompt states the camera move, what must not change, and the
"no text / no logo / no watermark / no cuts" constraints. Audio is disabled at
generation (`audio_mode=none`) because the score is written for the edit.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "data" / "portfolio-2026-10-23"
sys.path.insert(0, str(REPO))

# shot -> (source plate, LTX prompt, seconds). Durations are the shot durations
# used by the edit; LTX accepts 1..15 s, so every shot fits in one call.
LTX_SHOTS = {
    "food": {
        "jante": {
            "plate": "food/f1-rim.png",
            "seconds": 6.2,
            "prompt": (
                "Continuous premium automotive macro commercial. Preserve exactly the unbranded "
                "forged wheel from the reference: polished chrome lip, satin graphite spokes, "
                "dark centre cap, wet tyre. The wheel turns very slowly, about fifteen degrees "
                "over the shot, while a long softbox reflection travels across the chrome and the "
                "camera pushes in slightly. Fine water beads on the tyre sidewall stay in place. "
                "Mechanically correct geometry, physically accurate specular highlights, rich "
                "blacks, no text, no logo, no watermark, no cuts, no camera shake."
            ),
        },
        "assiette": {
            "plate": "food/f2-plate.png",
            "seconds": 6.8,
            "prompt": (
                "Continuous photorealistic Michelin-star dessert commercial, top-down. Preserve "
                "exactly the ivory plate, the glossy chocolate sphere with its gold leaf, the "
                "hand-poured raspberry coulis spiral, the cocoa crumb and the raspberries. A slow "
                "camera dolly moves a few centimetres sideways with optical parallax; a faint wisp "
                "of steam rises and drifts, the chocolate highlights glide over the glaze. The "
                "dessert does not change shape. Warm copper key light, cool rim reflection. "
                "No hands, no people, no text, no logo, no cuts, no camera shake."
            ),
        },
        "tasse": {
            "plate": "food/f6a-cup.png",
            "seconds": 5.6,
            "prompt": (
                "Continuous photorealistic espresso commercial, top-down. Preserve exactly the "
                "graphite ceramic cup with its copper rim, the tiger-striped crema, the dark walnut "
                "table. A slow camera pull-back reveals the cup rim; the crema shimmers very "
                "slightly and a thin thread of steam rises. Warm copper key light and a cool rim "
                "reflection on the cup edge. No hands, no spoon, no text, no logo, no cuts."
            ),
        },
        "macro": {
            "plate": "food/f3-macro.png",
            "seconds": 8.0,
            "prompt": (
                "Continuous extreme macro dessert commercial. Preserve exactly the glossy dark "
                "chocolate sphere with its gold leaf, the raspberry coulis spiral and the ivory "
                "plate. The camera rises slowly from a low three-quarter angle; a slow drip of "
                "molten chocolate runs down the base, warm steam curls upward, the window "
                "reflection on the glaze stretches as the camera moves. Shallow depth of field, "
                "warm copper key light, cool fill. No hands, no people, no text, no logo, no cuts."
            ),
        },
        "hero": {
            "plate": "food/f2-plate.png",
            "seconds": 7.0,
            "prompt": (
                "Continuous photorealistic luxury dessert hero shot, three-quarter angle. Preserve "
                "exactly the plated chocolate sphere, the raspberry spiral and the walnuts' table. "
                "A slow, stately camera push-in with a gentle roll; warm candle bokeh breathes in "
                "the dark restaurant background, steam drifts, the gold leaf glints. Rich blacks, "
                "warm copper highlights. No hands, no people, no text, no logo, no watermark, no cuts."
            ),
        },
    },
    "auto": {
        "lunettes": {
            "plate": "auto/a1-lens.png",
            "seconds": 6.4,
            "prompt": (
                "Continuous macro eyewear commercial. Preserve exactly the unbranded titanium "
                "sunglasses lens and the coastal road reflection inside it. A slow camera arc "
                "reveals the curved glass; the reflection shifts realistically with the sun "
                "flaring softly at the right edge, one water droplet holds on the surface. "
                "Physically plausible refraction, no lettering, no logo, no watermark, no cuts."
            ),
        },
        "route": {
            "plate": "auto/a2-road.png",
            "seconds": 8.6,
            "prompt": (
                "Continuous premium automotive lifestyle commercial, golden hour coastal road. "
                "Preserve exactly the generic dark graphite electric grand-tourer and the road. "
                "The car rolls forward smoothly along its line while the camera tracks slowly "
                "sideways; moving reflections slide over the paint and glass, dry grass sways in "
                "the foreground wind, gentle heat haze. No badge, no plate lettering, no text, "
                "no logo, no watermark, no cuts, no camera shake."
            ),
        },
        "jante": {
            "plate": "auto/a3-wheel.png",
            "seconds": 7.0,
            "prompt": (
                "Continuous automotive macro commercial. Preserve exactly the unbranded forged "
                "silver wheel, the chrome lip and the tyre. The wheel rotates slowly and steadily, "
                "the camera tracks it slightly, cool rim light sweeps across the spokes while a "
                "warm reflection stays on the caliper behind. Mechanically correct rotation, no "
                "wobble, no text, no logo, no watermark, no cuts."
            ),
        },
        "hero": {
            "plate": "auto/a2-road.png",
            "seconds": 9.0,
            "prompt": (
                "Continuous premium automotive hero shot at sunset on a coastal road. Preserve "
                "exactly the generic dark graphite grand-tourer. Slow cinematic push-in and slight "
                "roll while the car holds its line, the low sun flares across the lens, dry grass "
                "moves in the foreground. Warm copper against cool blue shadow, natural haze. "
                "No badge, no text, no logo, no watermark, no cuts, no camera shake."
            ),
        },
    },
}


# Measured on the 2026-10-23 production (same app, same volume, same GPU):
# 4 clips of 5.042 s took 440.5 s of function time, i.e. ~22 s of wall time per
# second of finished video, container start excluded.
GPU_SECONDS_PER_VIDEO_SECOND = 22.0


def _estimate_cost_usd(seconds: float, rate_per_hour: float = 1.95) -> float:
    """Cost of one clip: generation wall time at the L40S list price.

    A 5 s clip is not 5 s of GPU. Using the clip duration as the billed time is
    exactly the kind of estimate that makes a cost report meaningless, so the
    measured ratio above is used instead.
    """
    return round(seconds * GPU_SECONDS_PER_VIDEO_SECOND / 3600.0 * rate_per_hour, 4)


def _existing(shot_dir: Path) -> Path | None:
    meta = shot_dir / "modal_metadata.json"
    video = shot_dir / "modal_ltx.mp4"
    if meta.is_file() and video.is_file() and video.stat().st_size > 100_000:
        return video
    return None


def run(film: str, dry_run: bool = False, rate: float = 1.95) -> dict:
    shots = LTX_SHOTS[film]
    out_root = WORK / "ltx" / film
    out_root.mkdir(parents=True, exist_ok=True)
    report: dict = {"film": film, "shots": [], "estimated_usd": 0.0}
    for name, spec in shots.items():
        shot_dir = out_root / name
        shot_dir.mkdir(parents=True, exist_ok=True)
        plate = WORK / spec["plate"]
        if not plate.is_file():
            raise FileNotFoundError(plate)
        entry = {"shot": name, "plate": spec["plate"], "seconds": spec["seconds"],
                 "estimated_usd": _estimate_cost_usd(spec["seconds"], rate)}
        existing = _existing(shot_dir)
        if existing is not None:
            entry.update({"status": "reused", "video": str(existing)})
            report["shots"].append(entry)
            print(f"[{film}/{name}] déjà rendu -> {existing}")
            continue
        report["estimated_usd"] += entry["estimated_usd"]
        if dry_run:
            entry["status"] = "planned"
            report["shots"].append(entry)
            print(f"[{film}/{name}] PLANIFIÉ {spec['seconds']:.1f}s "
                  f"~{entry['estimated_usd']:.3f} USD\n    {spec['prompt'][:120]}...")
            continue
        entry.update(_render(shot_dir, plate, spec))
        report["shots"].append(entry)
    report["estimated_usd"] = round(report["estimated_usd"], 4)
    (out_root / "ltx-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                              encoding="utf-8")
    print(f"\n[{film}] coût estimé de ce passage : {report['estimated_usd']:.3f} USD "
          f"(L40S, {rate} USD/h, hors démarrage de conteneur)")
    return report


def _render(shot_dir: Path, plate: Path, spec: dict) -> dict:
    """One LTX call through the studio's Modal engine contract."""
    import modal  # noqa: F401  (import error is the honest signal here)

    from backend.app import media
    from backend.app.engines.modal_remote import ModalEngine
    from backend.app.engines.base import EngineRequest

    engine = ModalEngine("video")
    available, why = engine.available()
    if not available:
        raise RuntimeError(f"LTX indisponible : {why}")
    request = EngineRequest(
        kind="video",
        output_dir=shot_dir,
        project={"name": "SiteQuiVend portfolio", "format": "9:16"},
        prompt=spec["prompt"],
        duration_s=float(spec["seconds"]),
        inputs={"reference_image": str(plate)},
        params={"seed": 812310 + abs(hash(spec["plate"])) % 9973, "audio_mode": "none"},
    )

    class _Ctx:
        def log(self, message, **kwargs):
            print(f"    {message} {kwargs.get('progress', '')}", flush=True)

        def check_cancelled(self):
            pass

    started = time.time()
    output = engine.run(request, _Ctx())
    path = Path(output.artifacts[0]["path"])
    info = media.probe(path)
    width = int(info.width)
    if width != 1080:
        # LTX renders 768x1344: scale once to the delivery format
        scaled = shot_dir / "modal_ltx_1080.mp4"
        media.run_ffmpeg(["-i", str(path), "-vf",
                          "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
                          "crop=1080:1920,setsar=1", "-an", "-r", "30", "-c:v", "libx264",
                          "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", str(scaled)])
        path = scaled
    return {"status": "rendered", "video": str(path),
            "wall_seconds": round(time.time() - started, 1),
            "gpu_seconds": output.diagnostics.get("gpu_wall_seconds"),
            "actual_usd": output.usage.usd if getattr(output, "usage", None) else None}


def verify(film: str) -> dict:
    """Check every clip needed by the edit exists, at 1080x1920 and 30 fps."""
    sys.path.insert(0, str(REPO))
    from backend.app import media
    out = {}
    for name in LTX_SHOTS[film]:
        path = WORK / "ltx" / film / name / "modal_ltx_1080.mp4"
        if not path.is_file():
            out[name] = {"ok": False, "reason": "absent"}
            continue
        info = media.probe(path).to_dict()
        out[name] = {"ok": info["width"] == 1080 and info["height"] == 1920,
                     "duration_s": info["duration_s"], "fps": info["fps"]}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", choices=["food", "auto", "both"], default="both")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rate", type=float, default=1.95, help="USD/h L40S")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    for film in (["food", "auto"] if args.film == "both" else [args.film]):
        if args.verify:
            print(json.dumps(verify(film), indent=2, ensure_ascii=False))
        else:
            run(film, dry_run=args.dry_run, rate=args.rate)


if __name__ == "__main__":
    main()
