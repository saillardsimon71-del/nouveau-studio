"""Build the two SiteQuiVend portfolio films.

Examples
--------
    # verify the geometry of the morph circles on stills
    python -m scripts.portfolio.build --film food --debug-circles

    # inspect a few frames before paying for a full render
    python -m scripts.portfolio.build --film food --stills 3,8.2,14.6,22

    # full render (branded + clean), score, mux, QC, cover, metadata
    python -m scripts.portfolio.build --film food --full

Nothing here talks to Modal: the GPU path is `--ltx` (see scripts/portfolio/ltx_shots.py)
and is optional. The morph edit itself runs on CPU and is fully reproducible.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.portfolio.morphfilm import (  # noqa: E402
    derive, films, film as filmmod, imageops, morph, score,
)

WORK = REPO / "data" / "portfolio-2026-10-23"
FONTS = WORK / "fonts"


def get_film(slug: str, root: Path = WORK) -> filmmod.Film:
    return films.food(root) if slug == "food" else films.auto(root)


# --------------------------------------------------------------------------- stills


def _overlay_circle(img: np.ndarray, c: morph.Circle, colour=(90, 240, 160)) -> None:
    cv2.circle(img, (int(c.cx), int(c.cy)), int(c.r), colour, 4)
    cv2.drawMarker(img, (int(c.cx), int(c.cy)), colour, cv2.MARKER_CROSS, 60, 4)


def debug_circles(slug: str, out_dir: Path) -> None:
    """Draw the measured morph anchors on the endpoint frames (visual check)."""
    f = get_film(slug)
    renderer = filmmod.Renderer(f, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, tr in enumerate(f.transitions):
        plan = renderer.transition_plan(i)
        frames = {"a": renderer.shot_frame(i, 1.0), "b": renderer.shot_frame(i + 1, 0.0)}
        for side, img in frames.items():
            canvas = (np.clip(img, 0, 1) * 255).astype(np.uint8)
            canvas = cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR)
            if plan.kind in {"radial", "hybrid"}:
                for circle, colour in ((plan.ca, (90, 240, 150)), (plan.cb, (240, 190, 90))):
                    if circle is None:
                        continue
                    cv2.circle(canvas, (int(circle.cx), int(circle.cy)), int(circle.r), colour, 5)
                    cv2.drawMarker(canvas, (int(circle.cx), int(circle.cy)), colour,
                                   cv2.MARKER_CROSS, 80, 5)
            elif plan.ellipse is not None:
                cx, cy, ax, ay, ang = plan.ellipse
                cv2.ellipse(canvas, (int(cx), int(cy)), (int(ax), int(ay)), ang, 0, 360,
                            (90, 240, 150), 5)
                cv2.drawMarker(canvas, (int(cx), int(cy)), (90, 240, 150), cv2.MARKER_CROSS, 80, 5)
            else:
                cv2.drawMarker(canvas, (int(plan.center[0]), int(plan.center[1])),
                               (90, 240, 150), cv2.MARKER_CROSS, 90, 5)
            cv2.putText(canvas, f"{tr.name} {side}", (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.3,
                        (90, 240, 150), 3)
            cv2.imwrite(str(out_dir / f"{slug}-t{i}-{side}.png"), canvas)
        print(f"  {slug} t{i} {tr.name} anchors: {plan.ca} {plan.cb} {plan.ellipse}")


def morph_stills(slug: str, spec: str, out_dir: Path) -> None:
    """Render the morph itself at given progresses: `0:0.35,1:0.5` = tr 0 at w=0.35."""
    f = get_film(slug)
    renderer = filmmod.Renderer(f, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for item in spec.split(","):
        if ":" not in item:
            continue
        ti, ws = item.split(":")
        i, w = int(ti), float(ws)
        start = renderer.sched[i + 1][0]
        tr = f.transitions[i]
        t = start + w * tr.duration
        img, info = renderer.frame(t)
        img = imageops.apply_grade(img, f.grade, imageops.GrainBank(), grain_index=int(t * f.fps))
        path = out_dir / f"{slug}-morph{i}-w{w:.2f}.png"
        imageops.save(img, path)
        print(f"  morph {i} w={w:.2f} -> {path}")


def render_sheets(slug: str, out_dir: Path) -> None:
    """Contact sheets of every morph: the cheapest honest review possible."""
    from scripts.portfolio.morphfilm import morph
    f = get_film(slug)
    renderer = filmmod.Renderer(f, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, tr in enumerate(f.transitions):
        row = []
        for w in (0.0, 0.2, 0.4, 0.55, 0.7, 0.85, 1.0):
            img = morph.render_morph(renderer.transition_plan(i), renderer.shot_frame(i, 1.0),
                                     renderer.shot_frame(i + 1, 0.0), w)
            frame = (np.clip(img, 0, 1) * 255).astype(np.uint8)
            row.append(frame)
        strip = np.concatenate(
            [np.concatenate([im, np.full((im.shape[0], 6, 3), 40, np.uint8)], axis=1)
             for im in row], axis=1)
        path = out_dir / f"sheet-{slug}-{i}.png"
        cv2.imwrite(str(path), cv2.cvtColor(strip, cv2.COLOR_RGB2BGR))
        print(f"  sheet {slug} {i} ({tr.name}) -> {path}")


def render_stills(slug: str, times: list[float], out_dir: Path) -> None:
    f = get_film(slug)
    r = filmmod.Renderer(f, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    grain = imageops.GrainBank()
    for t in times:
        img, info = r.frame(t)
        img = imageops.apply_grade(img, f.grade, grain, grain_index=int(t * f.fps))
        path = out_dir / f"{slug}-t{t:05.2f}.png"
        imageops.save(img, path)
        print(f"  still {t:5.2f}s  {info}  -> {path}")


# --------------------------------------------------------------------------- audio


def build_score(f: filmmod.Film) -> Path:
    sched = f.schedule()
    cues = score.food_cue() if f.slug.startswith("sitequivend-food") else score.auto_cue()
    events: list[tuple[float, str]] = []
    for i, tr in enumerate(f.transitions):
        start = sched[i + 1][0]
        peak = start + tr.duration * 0.58
        events.append((peak, "whoosh"))
        events.append((start + tr.duration * 0.86, "boom"))
    # signature transition gets a riser; the end card gets a shimmer
    sig = 0 if f.slug.startswith("sitequivend-food") else len(f.transitions) - 1
    events.append((sched[sig + 1][0] + f.transitions[sig].duration * 0.55, "riser"))
    events.append((f.duration - f.endcard["duration"] + 0.15, "shimmer"))
    events.append((f.duration - f.endcard["duration"] + 0.05, "sparkle"))
    if f.slug.startswith("sitequivend-auto"):
        events.append((sched[2][0] + f.transitions[1].duration * 0.5, "rumble"))
    audio = score.render_cue(cues, f.duration, events)
    path = WORK / "audio" / f"{f.slug}-score.wav"
    score.write_wav(path, audio)
    print(f"  score -> {path}  ({audio.shape[0] / score.SR:.2f}s)")
    return path


# --------------------------------------------------------------------------- full


def finish(slug: str, stats: dict | None = None) -> dict:
    """Score, mux, QC, cover and metadata from the rendered picture.

    Kept separate from `full`: re-recording the music or a typo in the cover must
    never trigger a 10-minute frame render.
    """
    f = get_film(slug)
    build = WORK / "build"
    exports = WORK / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    audio = build_score(f)
    out_branded = exports / f"{f.slug}.mp4"
    out_clean = exports / f"{f.slug}-sans-signature.mp4"
    filmmod.mux(build / f"{f.slug}-branded.mp4", audio, out_branded, f.title,
                "Publicité premium générée et montée par SiteQuiVend.")
    filmmod.mux(build / f"{f.slug}-clean.mp4", audio, out_clean, f.title + " (sans signature)",
                "Version sans habillage. Publicité premium générée et montée par SiteQuiVend.")
    report = filmmod.qc_report(out_branded, f.fps, f.duration)
    (exports / f"{f.slug}.qc.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                              encoding="utf-8")
    cover_t = f.duration - f.endcard["duration"] - 4.2
    img, _ = filmmod.Renderer(f, build).frame(max(0.0, cover_t))
    img = imageops.apply_grade(img, f.grade, imageops.GrainBank(), grain_index=0)
    cover_lines = ([("Le désir,", 92), ("plan par plan.", 92)] if slug == "food"
                   else [("Le luxe", 92), ("se ressent.", 92)])
    kicker = "Food & Luxe" if slug == "food" else "Automotive & Lifestyle"
    filmmod.cover(img, exports / f"{f.slug}-cover.jpg", kicker, cover_lines, FONTS)
    return _metadata(f, stats or {}, out_branded, out_clean)


def _metadata(f, stats: dict, out_branded: Path, out_clean: Path) -> dict:
    exports = WORK / "exports"
    meta = {
        "brand": "SiteQuiVend",
        "slug": f.slug,
        "title": f.title,
        "duration_s": round(f.duration, 3),
        "fps": f.fps,
        "resolution": "1080x1920",
        "category": f.meta.get("category"),
        "concept": f.meta.get("concept"),
        "morph_count": f.meta.get("morph_count"),
        "shots": [{"name": s.name, "duration_s": s.duration} for s in f.shots],
        "transitions": [{"name": t.name, "kind": t.kind, "duration_s": t.duration}
                        for t in f.transitions],
        "schedule": [{"start": round(a, 3), "end": round(b, 3), "shot": f.shots[i].name}
                     for a, b, i in f.schedule()],
        "render": stats,
        "outputs": {},
        "engines": {
            "picture": "moteur morphfilm (CPU, Python/OpenCV/numpy) : plaques photographiques, "
                       "camera virtuelle 2.5D, morphs, etalonnage, grain, habillage",
            "plates": "images générées hors dépôt (outil imagegen), prompts conservés ci-dessous",
            "ltx": "LTX-2.5 / Modal kulejean567 : non exécutable depuis cet environnement "
                   "(TLS bloqué, aucun jeton Modal). Script prêt : scripts/portfolio/ltx_shots.py",
            "audio": "score original synthétisé (numpy/scipy), aucun sample tiers",
        },
        "cost": {"modal_usd": 0.0,
                 "note": "aucun GPU facturé : rendu local CPU. L'estimation du passage LTX est "
                         "dans scripts/portfolio/ltx_shots.py --dry-run (~0,40 USD par film)."},
        "prompts": f.meta.get("prompts"),
        "limitations": [
            "Plaques 768x1376 remontées en 1080x1920 (1,4x) : le grain et l'accentuation "
            "compensent, mais ce n'est pas une captation native.",
            "Mouvement 2.5D (caméra, parallaxe estimée, couches d'atmosphère) : pas de "
            "mouvement de sujet réel, faute de LTX disponible ici.",
            "Les morphs sont des effets de montage (rotation/zoom/portail/flare) et non des "
            "morphs générés par modèle ; le raccord est exact aux deux extrémités.",
            "Le studio IA historique n'est pas touché : tout est additif dans scripts/portfolio.",
        ],
        "derivations": derive.derive(WORK),
    }
    for path in (out_branded, out_clean, exports / f"{f.slug}-cover.jpg"):
        meta["outputs"][path.name] = {
            "bytes": path.stat().st_size,
            "sha256": filmmod.sha256(path),
            "probe": filmmod.probe(path),
        }
    (exports / f"{f.slug}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                                            encoding="utf-8")
    print(f"[{f.slug}] QC {filmmod.qc_report(out_branded, f.fps, f.duration)['verdict']} | "
          f"{out_branded.name} {out_branded.stat().st_size / 1e6:.1f} Mo")
    return meta


def full(slug: str) -> dict:
    t0 = time.time()
    f = get_film(slug)
    build = WORK / "build"
    exports = WORK / "exports"
    build.mkdir(parents=True, exist_ok=True)
    exports.mkdir(parents=True, exist_ok=True)
    branded = build / f"{f.slug}-branded.mp4"
    clean = build / f"{f.slug}-clean.mp4"
    print(f"[{slug}] {f.title}: {f.duration:.2f}s, {f.frames} frames, "
          f"{len(f.shots)} plans, {len(f.transitions)} morphs")
    stats = filmmod.Renderer(f, build).render(branded, clean, FONTS, f.endcard)
    stats["wall_seconds"] = round(time.time() - t0, 1)
    meta = finish(slug, stats)
    print(f"[{slug}] total {time.time() - t0:.0f}s")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", choices=["food", "auto", "both"], default="both")
    ap.add_argument("--stills", default="")
    ap.add_argument("--debug-circles", action="store_true")
    ap.add_argument("--morph-stills", default="")
    ap.add_argument("--sheets", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--finish", action="store_true",
                    help="score + mux + QC + cover + métadonnées sur le rendu existant")
    ap.add_argument("--score-only", action="store_true")
    args = ap.parse_args()
    slugs = ["food", "auto"] if args.film == "both" else [args.film]

    derive.derive(WORK)
    for slug in slugs:
        if args.debug_circles:
            debug_circles(slug, WORK / "debug")
        if args.sheets:
            render_sheets(slug, WORK / "stills")
        if args.morph_stills:
            morph_stills(slug, args.morph_stills, WORK / "stills")
        if args.stills:
            render_stills(slug, [float(x) for x in args.stills.split(",") if x.strip()],
                          WORK / "stills")
        if args.score_only:
            build_score(get_film(slug))
        if args.finish:
            finish(slug)
        if args.full:
            full(slug)


if __name__ == "__main__":
    main()
