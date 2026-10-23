"""The two portfolio films: timeline, moves, morph parameters, briefs.

Both films are 1080x1920, 30 fps, ~26-27 s. Each is built from photographic
plates, a virtual camera move per shot, and morph transitions between shots.
The LTX prompts that produced the plates are kept next to the timeline so the
same edit can be re-shot on GPU footage with the exact same timing.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from . import anchors, atmos, camera, film, imageops
from .film import Film, Shot, Transition, plate as plate_of
from .anchors import Endpoint

FPS = 30


# --------------------------------------------------------------------------- anchors


def _circle(slug: str, key: str, feature: str, ep, root: Path):
    """Anchor projected from the native measurement onto the endpoint frame.

    `build.py --debug-circles` renders the same endpoint frames with this circle
    drawn on top; if the projection is wrong for a shot, the overlay shows it
    before any render is spent.
    """
    return anchors.circle(feature, ep)


def _ellipse(slug: str, key: str, feature: str, ep, root: Path):
    return anchors.ellipse(feature, ep)


# --------------------------------------------------------------------------- post hooks


def _steam(t: float, cx: float, cy: float, width: float, height: float, strength: float):
    bank = atmos.Steam(seed=31)

    def post(img: np.ndarray, u: float) -> np.ndarray:
        return imageops.add_light(img, bank.render(t + u * 6.0, cx, cy, width, height, strength))
    return post


def _dust(seed: int, strength: float):
    bank = atmos.Dust(seed=seed)

    def post(img: np.ndarray, u: float) -> np.ndarray:
        return imageops.add_light(img, bank.render(u * 9.0, strength=strength))
    return post


def _flare(cx: float, cy: float, strength: float, radius: float, drift: float = 0.0):
    def post(img: np.ndarray, u: float) -> np.ndarray:
        flicker = 0.85 + 0.15 * math.sin(u * 11.0) * math.sin(u * 3.1)
        return imageops.add_light(
            img, atmos.flare((cx + drift * u * 30.0, cy), strength * flicker, radius=radius))
    return post


def _combine(*fns):
    def post(img: np.ndarray, u: float) -> np.ndarray:
        for fn in fns:
            img = fn(img, u)
        return img
    return post


# --------------------------------------------------------------------------- food


def food(root: Path, width: int = 1080, height: int = 1920) -> Film:
    rim = plate_of(root / "food" / "f1-rim.png", width, height, overscan=1.06)
    plate = plate_of(root / "food" / "f2-plate.png", width, height, depth=True)
    cup = plate_of(root / "food" / "f6a-cup.png", width, height)
    macro = plate_of(root / "food" / "f3-macro.png", width, height, depth=True)

    # camera state at the frames the morphs blend (see anchors.py)
    EP = {
        "rim_end": Endpoint(1.06, zoom=1.070, pan=(0.000, -0.003), roll=-1.0),
        "plate_start": Endpoint(1.24, zoom=1.030, pan=(-0.004, 0.004), roll=-1.3),
        "plate_end": Endpoint(1.24, zoom=1.130, pan=(0.004, -0.002), roll=0.7),
        "cup_start": Endpoint(1.24, zoom=1.140, pan=(0.005, 0.000), roll=0.8),
        "cup_end": Endpoint(1.24, zoom=1.040, pan=(-0.005, 0.000), roll=-0.8),
        "macro_start": Endpoint(1.24, zoom=1.160, pan=(0.000, -0.008), roll=-0.4),
        "macro_end": Endpoint(1.24, zoom=1.030, pan=(0.000, 0.006), roll=0.4),
        "hero_start": Endpoint(1.24, zoom=1.130, pan=(0.000, -0.004), roll=0.0),
    }

    resolves = {
        "rim_end": {"kind": "circle", "feature": "rim", "endpoint": EP["rim_end"],
                    "shot": 0, "u": 1.0, "dc": 110},
        "plate_start": {"kind": "circle", "feature": "plate", "endpoint": EP["plate_start"],
                        "shot": 1, "u": 0.0, "dc": 80},
        "plate_end": {"kind": "circle", "feature": "plate", "endpoint": EP["plate_end"],
                      "shot": 1, "u": 1.0, "dc": 80},
        "cup_start": {"kind": "circle", "feature": "cup", "endpoint": EP["cup_start"],
                      "shot": 2, "u": 0.0, "dc": 90},
        "cup_end": {"kind": "circle", "feature": "cup", "endpoint": EP["cup_end"],
                    "shot": 2, "u": 1.0, "dc": 90},
        "dome_start": {"kind": "circle", "feature": "dome", "endpoint": EP["macro_start"],
                       "shot": 3, "u": 0.0, "dc": 70},
        "dome_end": {"kind": "circle", "feature": "dome", "endpoint": EP["macro_end"],
                     "shot": 3, "u": 1.0, "dc": 70},
        "hero_start": {"kind": "circle", "feature": "plate", "endpoint": EP["hero_start"],
                       "shot": 4, "u": 0.0, "dc": 80},
    }

    shots = [
        Shot("jante", rim, 4.8, sweep=True,
             cam=lambda u: camera.Cam(zoom=1.015 + 0.055 * camera.ease_in_out(u),
                                      pan_y=0.006 - 0.010 * u,
                                      roll_deg=1.4 - 2.6 * camera.ease_in_out(u),
                                      parallax=0.03)),
        Shot("assiette", plate, 7.0,
             cam=lambda u: camera.Cam(zoom=1.03 + 0.10 * camera.ease_in_out(u),
                                      roll_deg=-1.3 + 2.0 * camera.ease_in_out(u),
                                      pan_x=-0.004 + 0.008 * u,
                                      pan_y=0.004 - 0.006 * u, parallax=0.02),
             post=_steam(0.0, 540, 940, 300, 620, 0.055)),
        Shot("tasse", cup, 5.4, sweep=True,
             cam=lambda u: camera.Cam(zoom=1.14 - 0.10 * camera.ease_in_out(u),
                                      roll_deg=0.8 - 1.6 * camera.ease_in_out(u),
                                      pan_x=0.005 - 0.010 * u),
             post=_steam(3.0, 540, 880, 210, 480, 0.050)),
        Shot("macro", macro, 7.8, sweep=True,
             cam=lambda u: camera.Cam(zoom=1.16 - 0.13 * camera.ease_in_out(u),
                                      pan_y=-0.008 + 0.014 * u,
                                      roll_deg=-0.4 + 0.8 * u,
                                      parallax=0.055, focus_shift=-0.30 + 0.50 * u),
             post=_steam(6.0, 540, 1010, 360, 700, 0.085)),
        Shot("hero", plate, 7.8, sweep=True,
             cam=lambda u: camera.Cam(zoom=1.13 - 0.13 * camera.ease_in_out(u),
                                      roll_deg=0.0 - 1.1 * camera.ease_in_out(u),
                                      pan_y=-0.004 + 0.004 * u, parallax=0.02),
             post=_steam(9.0, 540, 950, 320, 640, 0.045)),
    ]

    transitions = [
        # signature transition: the wheel spins up and pushes through the lens,
        # the plate arrives still turning and settles. No blending, no ghosting.
        Transition("jante->assiette", "spin", 1.1, params={
            "ca": _circle("food", "rim_end", "rim", EP["rim_end"], root),
            "cb": _circle("food", "plate_start", "plate", EP["plate_start"], root),
            "spin": 66.0, "zoom": 1.68, "flash": 0.62,
            "warm": (1.0, 0.80, 0.55), "light": "sweep"},
            drift=0.07, drift_dir=(0.0, -0.004)),
        Transition("assiette->tasse", "zoom", 1.5, params={
            "ca": _circle("food", "plate_end", "plate", EP["plate_end"], root),
            "cb": _circle("food", "cup_start", "cup", EP["cup_start"], root),
            "depth": 2.35, "light": "sweep"},
            drift=0.07, drift_dir=(0.0, 0.0)),
        Transition("tasse->macro", "spin", 1.0, params={
            "ca": _circle("food", "cup_end", "cup", EP["cup_end"], root),
            "cb": _circle("food", "dome_start", "dome", EP["macro_start"], root),
            "spin": 34.0, "zoom": 1.50, "flash": 0.45,
            "warm": (1.0, 0.74, 0.46), "light": "sweep"},
            drift=0.05, drift_dir=(0.0, 0.006)),
        Transition("macro->hero", "bloom", 1.6, params={
            "measure": ("dome", None), "warm": (1.0, 0.74, 0.40), "streak": 1.0,
            "light": "flare", "flare_center": (620, 1200)},
            drift=0.08, drift_dir=(0.0, -0.006)),
    ]

    grade = imageops.Grade(exposure=1.0, contrast=1.08, saturation=1.07, temperature=0.045,
                           shadow_tint=(-0.012, 0.0, 0.018),
                           highlight_tint=(0.022, 0.004, -0.018),
                           bloom=0.12, halation=0.09, grain=0.020, vignette=0.22, ca=0.45)
    film = Film(
        slug="sitequivend-food-luxe",
        title="SiteQuiVend — Food & Luxe",
        shots=shots, transitions=transitions, fps=FPS, grade=grade,
        endcard={"kicker": "Food & Luxe", "line": "Parlons de votre projet.",
                 "note": "Visuels générés par IA  ·  SiteQuiVend", "duration": 3.0},
        meta={
            "category": "food / luxury",
            "concept": "La jante devient assiette, l'assiette devient tasse, la tasse devient chocolat.",
            "morph_count": len(transitions),
            "prompts": FOOD_PROMPTS,
        },
    )
    film.endpoints = resolves
    return film


# --------------------------------------------------------------------------- automotive


def auto(root: Path, width: int = 1080, height: int = 1920) -> Film:
    lens = plate_of(root / "auto" / "a1-lens.png", width, height, depth=True)
    road = plate_of(root / "auto" / "a2-road.png", width, height, depth=True)
    wheel = plate_of(root / "auto" / "a3-wheel.png", width, height, overscan=1.12)

    sun = (958, 742)
    EP = {
        "lens_end": Endpoint(1.24, zoom=1.240, pan=(0.004, -0.004), roll=-1.0),
        "lens_start": Endpoint(1.24, zoom=1.030, pan=(-0.004, 0.004)),
        "road_start": Endpoint(1.24, zoom=1.100, pan=(0.006, -0.006)),
        "road_end": Endpoint(1.24, zoom=1.000, pan=(-0.006, 0.000)),
        "wheel_start": Endpoint(1.12, zoom=1.050, pan=(0.000, 0.000), roll=-5.0),
        "wheel_end": Endpoint(1.12, zoom=1.080, pan=(0.006, -0.004), roll=7.0),
        "hero_start": Endpoint(1.24, zoom=1.160, pan=(-0.004, 0.004), roll=0.5),
    }
    resolves = {
        "lens_end": {"kind": "ellipse", "feature": "lens", "endpoint": EP["lens_end"],
                     "shot": 0, "u": 1.0, "dc": 70, "da": 0.10},
        "wheel_end": {"kind": "circle", "feature": "wheel", "endpoint": EP["wheel_end"],
                      "shot": 2, "u": 1.0, "dc": 90},
        "reflect_end": {"kind": "circle", "feature": "reflect", "endpoint": EP["lens_end"],
                        "shot": 0, "u": 1.0, "dc": 70},
        "road_start": {"kind": "circle", "feature": "road", "endpoint": EP["road_start"],
                       "shot": 1, "u": 0.0, "dc": 90},
    }

    shots = [
        Shot("lunettes", lens, 5.8, sweep=True,
             cam=lambda u: camera.Cam(zoom=1.03 + 0.21 * camera.ease_in_out(u),
                                      roll_deg=1.0 - 2.0 * camera.ease_in_out(u),
                                      pan_y=0.004 - 0.008 * u, pan_x=-0.004 + 0.008 * u,
                                      parallax=0.05),
             post=_combine(_flare(sun[0], sun[1], 0.10, 480.0, drift=0.4),
                           _dust(21, 0.10))),
        Shot("route", road, 9.0, sweep=True,
             cam=lambda u: camera.Cam(zoom=1.10 - 0.10 * camera.ease_in_out(u),
                                      pan_x=0.006 - 0.012 * u,
                                      roll_deg=0.4 - 0.8 * camera.ease_in_out(u),
                                      pan_y=-0.006 + 0.006 * u, parallax=0.04),
             post=_combine(_flare(966, 760, 0.16, 640.0, drift=0.5),
                           _dust(33, 0.16))),
        Shot("jante", wheel, 6.6, sweep=True,
             cam=lambda u: camera.Cam(zoom=1.17 - 0.09 * camera.ease_in_out(u),
                                      roll_deg=-7.0 + 14.0 * camera.ease_in_out(u),
                                      pan_x=-0.006 + 0.012 * u, pan_y=0.004 - 0.008 * u,
                                      parallax=0.03)),
        Shot("hero", road, 10.0, sweep=True,
             cam=lambda u: camera.Cam(zoom=1.16 - 0.16 * camera.ease_in_out(u),
                                      roll_deg=0.5 - 1.0 * camera.ease_in_out(u),
                                      pan_x=-0.004 + 0.006 * u,
                                      pan_y=0.004 - 0.008 * u, parallax=0.05),
             post=_combine(_flare(966, 790, 0.13, 600.0, drift=0.3),
                           _dust(45, 0.12))),
    ]

    transitions = [
        # The opening is a macro on one lens: the reflection *is* the coast road
        # we cut to. So we dive through the reflection's road instead of opening
        # an aperture on a lens that already fills the frame (a portal there has
        # no room to grow and reads as a cut).
        Transition("lunettes->route", "zoom", 1.7, params={
            "ca": _circle("auto", "lens_end", "reflect", EP["lens_end"], root),
            "cb": _circle("auto", "road_start", "road", EP["road_start"], root),
            "depth": 2.5, "light": "flare", "flare_center": (900, 800)},
            drift=0.10, drift_dir=(-0.006, 0.004)),
        Transition("route->jante", "bloom", 1.5, params={
            "center": sun, "warm": (1.0, 0.70, 0.36), "streak": 1.0,
            "light": "flare", "flare_center": sun},
            drift=0.08, drift_dir=(0.0, 0.0)),
        Transition("jante->hero", "zoom", 1.5, params={
            "ca": _circle("auto", "wheel_end", "wheel", EP["wheel_end"], root),
            "cb": _circle("auto", "hero_start", "road", EP["hero_start"], root),
            "depth": 2.3, "light": "sweep"},
            drift=0.09, drift_dir=(0.0, -0.004)),
    ]

    grade = imageops.Grade(exposure=1.0, contrast=1.10, saturation=1.05, temperature=0.02,
                           shadow_tint=(-0.014, 0.002, 0.022),
                           highlight_tint=(0.026, 0.008, -0.014),
                           bloom=0.10, halation=0.06, grain=0.019, vignette=0.26, ca=0.55)
    film = Film(
        slug="sitequivend-automotive-lifestyle",
        title="SiteQuiVend — Automotive & Lifestyle",
        shots=shots, transitions=transitions, fps=FPS, grade=grade,
        endcard={"kicker": "Automotive & Lifestyle", "line": "Parlons de votre projet.",
                 "note": "Visuels générés par IA  ·  SiteQuiVend", "duration": 3.0},
        meta={
            "category": "automotive / lifestyle",
            "concept": "Le reflet des lunettes devient la route, le soleil devient la jante, la jante devient le voyage.",
            "morph_count": len(transitions),
            "prompts": AUTO_PROMPTS,
        },
    )
    film.endpoints = resolves
    return film


# --------------------------------------------------------------------------- briefs

FOOD_PROMPTS = {
    "f1-rim": (
        "Photorealistic luxury advertising still, vertical 9:16. Extreme close-up of an "
        "unbranded forged multi-spoke sports wheel, mirror-chrome outer lip, satin graphite "
        "spokes, perfectly centred, near-black studio background with a warm copper glow and "
        "a narrow cool-blue rim light. Long softbox reflections, realistic brake dust and "
        "water beads on the tyre. No car body, no logo, no lettering, no watermark."
    ),
    "f2-plate": (
        "Photorealistic Michelin-star dessert still, vertical 9:16, shot straight down. "
        "Circular ivory plate centred, filling 80% of the width, glossy dark chocolate sphere "
        "with gold leaf, hand-poured spiral of raspberry coulis, cocoa crumb, three raspberries, "
        "dark walnut table, warm copper key light, faint steam. No hands, no text, no logo."
    ),
    "f3-macro": (
        "Photorealistic extreme macro of the same dessert from a low three-quarter angle, "
        "mirror-glossy chocolate with a window reflection, slow molten drip, warm steam, dark "
        "restaurant bokeh, 100mm macro at f/2.8, copper key and cool fill. No text, no logo."
    ),
    "f6a-cup": (
        "Photorealistic luxury espresso still, vertical 9:16, top-down. Small graphite cup with "
        "a copper rim, perfectly circular and centred, tiger-striped crema, dark walnut table, "
        "copper key light and cool rim reflection, faint steam. No spoon, no text, no logo."
    ),
    "ltx-video": (
        "Slow continuous camera push over the still, preserve exact geometry and material, "
        "moving specular highlights, faint rising steam, no cuts, no text, no logo."
    ),
}

AUTO_PROMPTS = {
    "a1-lens": (
        "Photorealistic macro of a premium unbranded sport sunglasses lens, vertical 9:16, "
        "thin matte titanium frame, inside the lens a sharp physically plausible reflection of "
        "a winding coastal road at golden hour, low warm sun, ocean horizon, slight blue-green "
        "lens tint, dust and one water droplet. No lettering, no logo, no watermark."
    ),
    "a2-road": (
        "Photorealistic automotive lifestyle still, vertical 9:16. Winding coastal road at golden "
        "hour, low sun right, deep blue sky, distant mountains, guardrail and dry grass in the "
        "foreground. A generic premium electric grand-tourer with smooth minimal surfaces, no "
        "grille, thin light bar, dark graphite paint, front three-quarter. No badge, no plate "
        "lettering, no existing manufacturer resemblance, no text, no watermark."
    ),
    "a3-wheel": (
        "Derived from the food wheel master: rotated 96 degrees, tighter crop, cool silver grade. "
        "Same unbranded forged wheel, chrome lip, cool rim light."
    ),
    "ltx-video": (
        "Slow cinematic push along the road with the car holding its line, moving reflections on "
        "paint and glass, gentle heat haze, no cuts, no text, no logo."
    ),
}
