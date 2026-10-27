"""Morph anchors: measured in the native 768x1376 plates, projected exactly.

The morph circles must land on the frames the morph actually blends, i.e. the
endpoint frames including the camera zoom, pan and roll of each shot. Rather than
re-detecting a rim on every render (fragile on glossy, partly cropped objects),
the anchors are measured once on a 100 px grid over the plates, then projected
through the exact inverse of `camera.Plate.render`:

    q  = (nx * K * s - 540*s , ny * K * s - 960*s)
    x  = 540 + pan_x * 1080 + z * ( cos(r) * qx + sin(r) * qy )
    y  = 960 + pan_y * 1920 + z * ( -sin(r) * qx + cos(r) * qy )

with K = 1080/768, s the plate overscan, z the zoom and r the roll.

`scripts/portfolio/build.py --debug-circles` renders the endpoint frames with
these anchors drawn on top, so the numbers are checked by eye before a render is
spent. The radial radius is scaled by K * s * z, which is exact for the zoom, pan
and roll used here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .morph import Circle

K = 1080.0 / 768.0
OUT_W, OUT_H = 1080.0, 1920.0

# Measured on a 100 px grid over each native plate (debug/cand-*.png).
# Each entry: (cx, cy, radius) in the 768x1376 plate.
NATIVE_CIRCLES = {
    # polished inner lip of the wheel: where the spokes meet the rim
    "rim": (398.0, 691.0, 405.0),
    # outer edge of the porcelain plate
    "plate": (387.0, 760.0, 400.0),
    # crema surface inside the espresso cup
    "cup": (390.0, 660.0, 195.0),
    # dark chocolate sphere silhouette in the macro plate
    "dome": (388.0, 855.0, 218.0),
    # a1-lens: the coast road inside the reflection, the dive point of the zoom
    "reflect": (505.0, 700.0, 108.0),
    # a2-road: the car's front-left quarter, where the zoom lands
    "road": (330.0, 715.0, 168.0),
}
# cx, cy, ax, ay, angle (the sunglasses lens interior)
NATIVE_ELLIPSES = {
    "lens": (486.0, 700.0, 352.0, 452.0, 6.0),
}
# a3-wheel is derived from f1-rim: crop 84% + dx 5% + dy -1%, then resampled
DERIVE_CROP = (0.84, 0.05, -0.01)
DERIVE_SOURCE = "rim"


def _derive(native: tuple[float, float, float]) -> tuple[float, float, float]:
    scale, dx, dy = DERIVE_CROP
    w, h = 768.0, 1376.0
    nw, nh = w * scale, h * scale
    x0 = (w - nw) / 2.0 + dx * w
    y0 = (h - nh) / 2.0 + dy * h
    kv = w / nw
    cx, cy, r = native
    return (cx - x0) * kv, (cy - y0) * kv, r * kv


@dataclass
class Endpoint:
    """Camera state at the exact frame the morph blends (u=1 of A, u=0 of B)."""

    overscan: float = 1.24
    zoom: float = 1.0
    pan: tuple[float, float] = (0.0, 0.0)
    roll: float = 0.0


def _project(nx: float, ny: float, ep: Endpoint) -> tuple[float, float]:
    s, z = ep.overscan, ep.zoom
    qx = nx * K * s - OUT_W / 2 * s
    qy = ny * K * s - OUT_H / 2 * s
    r = math.radians(ep.roll)
    c, sn = math.cos(r), math.sin(r)
    x = OUT_W / 2 + ep.pan[0] * OUT_W + z * (c * qx + sn * qy)
    y = OUT_H / 2 + ep.pan[1] * OUT_H + z * (-sn * qx + c * qy)
    return x, y


def circle(name: str, ep: Endpoint) -> Circle:
    native = _derive(NATIVE_CIRCLES[DERIVE_SOURCE]) if name == "wheel" else NATIVE_CIRCLES[name]
    cx, cy, r = native
    x, y = _project(cx, cy, ep)
    return Circle(x, y, r * K * ep.overscan * ep.zoom)


def ellipse(name: str, ep: Endpoint) -> tuple[float, float, float, float, float]:
    cx, cy, ax, ay, ang = NATIVE_ELLIPSES[name]
    x, y = _project(cx, cy, ep)
    f = K * ep.overscan * ep.zoom
    return x, y, ax * f, ay * f, ang
