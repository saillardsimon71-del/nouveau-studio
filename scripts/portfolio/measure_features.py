"""Measure the circular features used by the morphs, with visual verification.

A morph anchored 20 px off reads as a glitch, so the anchors are measured, not
guessed. Each feature uses the strategy that actually works on that plate
(bright-ring ray casting, chroma blobs, ellipse fit on the lens rim), and every
fit is drawn on a check image under `debug/fit-*.png`. The numbers are only kept
once the overlay sits on the feature.

    python scripts/portfolio/measure_features.py            # all + geometry.json
    python scripts/portfolio/measure_features.py --show rim cup
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "data" / "portfolio-2026-10-23"
DEBUG = WORK / "debug"
RENDER = 1080.0 / 768.0          # native 768 px wide -> delivery 1080 px wide


def _img(rel: str) -> np.ndarray:
    img = cv2.imread(str(WORK / rel), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(rel)
    return img


def _robust_ellipse(pts: np.ndarray, rounds: int = 4) -> tuple[float, float, float, float, float]:
    keep = pts.astype(np.float32)
    for _ in range(rounds):
        (cx, cy), (d1, d2), ang = cv2.fitEllipse(keep.reshape(-1, 1, 2))
        t = np.deg2rad(ang)
        dx, dy = keep[:, 0] - cx, keep[:, 1] - cy
        u = dx * np.cos(t) + dy * np.sin(t)
        v = -dx * np.sin(t) + dy * np.cos(t)
        rn = np.sqrt((u / (d1 / 2)) ** 2 + (v / (d2 / 2)) ** 2)
        err = np.abs(rn - 1.0)
        mad = np.median(np.abs(err - np.median(err))) + 1e-6
        keep = keep[err < np.median(err) + 2.5 * mad]
        if len(keep) < 12:
            break
    (cx, cy), (d1, d2), ang = cv2.fitEllipse(keep.reshape(-1, 1, 2))
    return float(cx), float(cy), float(d1 / 2), float(d2 / 2), float(ang)


def _ring_points(img: np.ndarray, cx: float, cy: float, r_min: float, r_max: float,
                 channel: str = "v", mode: str = "max", samples: int = 720) -> np.ndarray:
    """Cast rays and keep the strongest (or weakest) sample: a bright/dark ring."""
    if channel == "v":
        plane = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32)
    elif channel == "s":
        plane = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1].astype(np.float32)
    else:
        plane = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    plane = cv2.GaussianBlur(plane, (0, 0), 2.0)
    h, w = plane.shape
    rs = np.arange(r_min, r_max, 1.0, dtype=np.float32)
    angs = np.linspace(0, 2 * np.pi, samples, endpoint=False, dtype=np.float32)
    xs = cx + np.cos(angs)[:, None] * rs[None, :]
    ys = cy + np.sin(angs)[:, None] * rs[None, :]
    vals = cv2.remap(plane, xs.astype(np.float32), ys.astype(np.float32), cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_REPLICATE)
    idx = np.argmax(vals, axis=1) if mode == "max" else np.argmin(vals, axis=1)
    px, py = xs[np.arange(len(angs)), idx], ys[np.arange(len(angs)), idx]
    inside = (px > 3) & (px < w - 4) & (py > 3) & (py < h - 4)
    return np.stack([px[inside], py[inside]], axis=1)


def _blob(img: np.ndarray, lo, hi, min_area: int, roi=None) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
    if roi is not None:
        keep = np.zeros_like(mask)
        cv2.ellipse(keep, roi[0], roi[1], roi[2], 0, 360, 255, -1)
        mask = cv2.bitwise_and(mask, keep)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnts = [c for c in cnts if cv2.contourArea(c) >= min_area]
    if not cnts:
        raise RuntimeError("no blob")
    return max(cnts, key=cv2.contourArea)


# --------------------------------------------------------------------------- features


def rim() -> dict:
    """Chrome lip of the wheel (brightest ring), measured by ray casting."""
    img = _img("food/f1-rim.png")
    pts = _ring_points(img, 396.0, 690.0, 300.0, 600.0, channel="v", mode="max")
    cx, cy, a, b, ang = _robust_ellipse(pts)
    # the wheel is a real circle seen almost head-on: keep it circular
    r = (a + b) / 2.0
    return {"cx": round(cx, 1), "cy": round(cy, 1), "radius": round(r, 1),
            "rx": round(a, 1), "ry": round(b, 1), "angle": round(ang, 1), "points": len(pts)}


def plate() -> dict:
    """Outer edge of the white plate (bright blob on a dark table)."""
    img = _img("food/f2-plate.png")
    cnt = _blob(img, (0, 0, 120), (60, 110, 255), 60000)
    cx, cy, a, b, ang = _robust_ellipse(cnt.reshape(-1, 2))
    return {"cx": round(cx, 1), "cy": round(cy, 1), "radius": round((a + b) / 2, 1),
            "rx": round(a, 1), "ry": round(b, 1), "angle": round(ang, 1)}


def cup() -> dict:
    """Crema surface: warm, saturated blob inside the cup."""
    img = _img("food/f6a-cup.png")
    cnt = _blob(img, (4, 80, 30), (34, 255, 240), 20000,
                roi=((392, 700), (230, 230), 0))
    cx, cy, a, b, ang = _robust_ellipse(cnt.reshape(-1, 2))
    return {"cx": round(cx, 1), "cy": round(cy, 1), "radius": round((a + b) / 2, 1),
            "rx": round(a, 1), "ry": round(b, 1), "angle": round(ang, 1)}


def dome() -> dict:
    """Chocolate sphere in the macro plate: dark, saturated, circular."""
    img = _img("food/f3-macro.png")
    cnt = _blob(img, (0, 55, 15), (30, 255, 95), 40000,
                roi=((392, 810), (250, 270), 0))
    x, y, w, h = cv2.boundingRect(cnt)
    r = (w + h) / 4.0
    return {"cx": round(x + w / 2.0, 1), "cy": round(y + h / 2.0, 1), "radius": round(r, 1),
            "bbox": [int(x), int(y), int(w), int(h)]}


def lens() -> dict:
    """Interior of the sunglasses lens: bright reflection region, tilted ellipse."""
    img = _img("auto/a1-lens.png")
    v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2]
    mask = (v > 62).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((11, 11), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    big = max(cnts, key=cv2.contourArea)
    (cx, cy), (a, b), ang = cv2.fitEllipse(big)
    # widen slightly: the aperture must sit just inside the rim, and the fit is
    # computed on the bright interior, not on the titanium frame
    return {"cx": round(float(cx), 1), "cy": round(float(cy), 1),
            "rx": round(float(a / 2 * 1.02), 1), "ry": round(float(b / 2 * 1.03), 1),
            "angle": round(float(ang), 1)}


def wheel_auto() -> dict:
    img = _img("auto/a3-wheel.png")
    # recompute from the derivation transform: crop 84% + shift, then resample
    scale = 0.84
    h, w = img.shape[:2]
    nw, nh = int(w * scale), int(h * scale)
    x0 = (w - nw) / 2.0 + 0.05 * w
    y0 = (h - nh) / 2.0 - 0.01 * h
    k = w / nw
    base = rim()
    return {"cx": round((base["cx"] - x0) * k, 1), "cy": round((base["cy"] - y0) * k, 1),
            "radius": round(base["radius"] * k, 1), "derived_from": "rim"}


FEATURES = {"rim": rim, "plate": plate, "cup": cup, "dome": dome, "lens": lens,
            "wheel_auto": wheel_auto}
SOURCES = {"rim": "food/f1-rim.png", "plate": "food/f2-plate.png", "cup": "food/f6a-cup.png",
           "dome": "food/f3-macro.png", "lens": "auto/a1-lens.png",
           "wheel_auto": "auto/a3-wheel.png"}


def overlay(name: str, geo: dict) -> Path:
    img = _img(SOURCES[name])
    cv2.ellipse(img, (int(geo["cx"]), int(geo["cy"])),
                (int(geo.get("rx", geo.get("radius", 0))), int(geo.get("ry", geo.get("radius", 0)))),
                geo.get("angle", 0.0), 0, 360, (60, 255, 120), 4)
    cv2.drawMarker(img, (int(geo["cx"]), int(geo["cy"])), (60, 255, 120), cv2.MARKER_CROSS, 60, 4)
    DEBUG.mkdir(parents=True, exist_ok=True)
    path = DEBUG / f"fit-{name}.png"
    cv2.imwrite(str(path), img)
    return path


def to_render(geo: dict) -> dict:
    """Native 768-wide coordinates -> delivery 1080x1920 coordinates."""
    out = {"cx": round(geo["cx"] * RENDER, 1), "cy": round(geo["cy"] * RENDER, 1)}
    if "radius" in geo:
        out["r"] = round(geo["radius"] * RENDER, 1)
    if "rx" in geo:
        out["rx"] = round(geo["rx"] * RENDER, 1)
        out["ry"] = round(geo["ry"] * RENDER, 1)
        out["angle"] = geo.get("angle", 0.0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", nargs="*", default=None)
    args = ap.parse_args()
    names = args.show or list(FEATURES)
    geo_out, render_out = {}, {}
    for name in names:
        try:
            geo = FEATURES[name]()
        except Exception as exc:
            print(f"{name}: FAILED ({exc})")
            continue
        geo_out[name] = geo
        render_out[name] = to_render(geo)
        print(f"{name}: {json.dumps(geo)}  -> {overlay(name, geo)}")
    print("\n# coordonnées livraison 1080x1920 (à recopier dans films.py)")
    for name, geo in render_out.items():
        print(f"{name:11s} {geo}")
    if not args.show:
        DEBUG.mkdir(parents=True, exist_ok=True)
        (DEBUG / "geometry.json").write_text(
            json.dumps({"native": geo_out, "render": render_out}, indent=2), encoding="utf-8")
        print(f"\nwritten {DEBUG / 'geometry.json'}")


if __name__ == "__main__":
    main()
