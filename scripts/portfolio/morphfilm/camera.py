"""Virtual camera: overscanned plates, sub-pixel moves, depth-aware parallax.

A shot never stores frames, it stores a *move*: a pure function of time that
returns the camera state (zoom, pan, roll). The morph transitions rely on that:
both shots keep moving while they are transformed into each other, which is what
makes a morph feel like one continuous camera move instead of a cross-dissolve.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import imageops


@dataclass
class Cam:
    zoom: float = 1.0
    pan_x: float = 0.0       # in output widths
    pan_y: float = 0.0       # in output heights
    roll_deg: float = 0.0
    parallax: float = 0.0    # 0 = flat plate, 0.05 = gentle, 0.12 = macro
    focus_shift: float = 0.0  # + = focus moves to the background


def ease_in_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1.0 - (1.0 - x) ** 3


def ease_in(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x ** 3


def smooth_step(x: float, a: float, b: float) -> float:
    if b <= a:
        return 1.0 if x >= b else 0.0
    return ease_in_out((x - a) / (b - a))


class Plate:
    """An overscanned image (and optional depth prior) used by a shot."""

    def __init__(self, path, width: int, height: int, overscan: float = 1.24,
                 depth: bool = False, grade_fn=None):
        self.width, self.height = width, height
        self.overscan = overscan
        self.img = imageops.load_cover(path, width, height, overscan=overscan)
        if grade_fn is not None:
            self.img = np.clip(grade_fn(self.img), 0.0, 1.0)
        # the depth prior is low frequency: keep it at output resolution so the
        # displacement maps and the focus drift share one coordinate system
        self.depth = (cv2.resize(imageops.estimate_depth(self.img), (width, height),
                                 interpolation=cv2.INTER_AREA) if depth else None)
        self.h, self.w = self.img.shape[:2]
        self._xx, self._yy = np.meshgrid(np.arange(self.width, dtype=np.float32),
                                         np.arange(self.height, dtype=np.float32))

    def render(self, cam: Cam) -> np.ndarray:
        W, H = self.width, self.height
        xx, yy = self._xx, self._yy
        # output pixel -> canvas pixel, inverse of the camera transform
        dx = xx - (W / 2.0 + cam.pan_x * W)
        dy = yy - (H / 2.0 + cam.pan_y * H)
        if cam.parallax > 0 and self.depth is not None:
            # near pixels (depth -> 1) shift more, giving real-looking parallax
            par = (0.5 - self.depth) * cam.parallax * (cam.zoom - 1.0) * 1.6
            scale = 1.0 / cam.zoom + par / max(1e-3, cam.zoom)
        else:
            scale = 1.0 / cam.zoom
        qx = dx * scale
        qy = dy * scale
        if abs(cam.roll_deg) > 1e-4:
            t = np.deg2rad(cam.roll_deg)
            c, s = np.cos(t), np.sin(t)
            qx, qy = qx * c - qy * s, qx * s + qy * c
        mx = (qx + self.w / 2.0).astype(np.float32, copy=False)
        my = (qy + self.h / 2.0).astype(np.float32, copy=False)
        out = cv2.remap(self.img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        if self.depth is not None and abs(cam.focus_shift) > 1e-4:
            out = depth_focus(out, self.depth, cam.focus_shift)
        return out


def depth_focus(img: np.ndarray, depth: np.ndarray, shift: float) -> np.ndarray:
    """Very small DOF drift: blur where the plane of focus is not.

    `shift` in [-1, 1]; +1 focuses on the background, -1 on the foreground.
    """
    h, w = img.shape[:2]
    small = cv2.resize(img, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 2.4)
    blur = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    plane = 0.5 - shift * 0.45
    amount = np.clip(np.abs(depth - plane) * 2.2 * abs(shift), 0.0, 0.85)[..., None]
    return img * (1 - amount) + blur * amount
