"""Image primitives for the SiteQuiVend portfolio films.

Everything is float32 RGB in [0, 1] (display-referred, gamma encoded) at the
delivery size 1080x1920. Three rules keep the look coherent:

* one shared film grade per film (warm copper highlights, cool blue shadows),
* grain and vignette are applied once, at the very end of each frame, so that a
  morph never blends two different grain structures,
* bloom / halation are computed on a downscaled copy: cheap and stable.

The module deliberately avoids heavy dependencies: numpy, OpenCV, Pillow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

W, H = 1080, 1920


# --------------------------------------------------------------------------- loads


def load_cover(path: str | Path, width: int = W, height: int = H, overscan: float = 1.0,
               sharpen: bool = True) -> np.ndarray:
    """Load an image, cover-fit it to `width*overscan x height*overscan`.

    Generated stills are 768x1376; the 1.40x upscale is done once here with a
    Lanczos kernel plus a light unsharp mask, never per frame.
    """
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    tw, th = int(round(width * overscan)), int(round(height * overscan))
    scale = max(tw / img.shape[1], th / img.shape[0])
    nw, nh = int(round(img.shape[1] * scale)), int(round(img.shape[0] * scale))
    interp = cv2.INTER_LANCZOS4 if scale > 1.0 else cv2.INTER_AREA
    img = cv2.resize(img, (nw, nh), interpolation=interp)
    x0, y0 = (nw - tw) // 2, (nh - th) // 2
    img = img[y0:y0 + th, x0:x0 + tw]
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    if sharpen and scale > 1.05:
        img = unsharp(img, amount=0.55, radius=1.0)
    return np.clip(img, 0.0, 1.0)


def save(img: np.ndarray, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = (np.clip(img, 0, 1) * 255.0 + 0.5).astype(np.uint8)
    cv2.imwrite(str(path), cv2.cvtColor(out, cv2.COLOR_RGB2BGR))


def unsharp(img: np.ndarray, amount: float = 0.5, radius: float = 1.0) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), radius)
    return np.clip(img + amount * (img - blur), 0.0, 1.0)


def luma(img: np.ndarray) -> np.ndarray:
    return (img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722)


# --------------------------------------------------------------------------- grade


@dataclass
class Grade:
    """A restrained cinema look: warm highlights, cool shadows, film grain."""

    exposure: float = 1.0
    contrast: float = 1.06
    pivot: float = 0.42
    saturation: float = 1.03
    temperature: float = 0.04      # + = warmer
    tint: float = 0.0              # + = magenta
    lift: tuple[float, float, float] = (0.0, 0.0, 0.0)
    gamma: tuple[float, float, float] = (1.0, 1.0, 1.0)
    shadow_tint: tuple[float, float, float] = (-0.010, 0.0, 0.016)
    highlight_tint: tuple[float, float, float] = (0.020, 0.004, -0.016)
    bloom: float = 0.10
    bloom_threshold: float = 0.72
    halation: float = 0.07
    grain: float = 0.020
    vignette: float = 0.20
    ca: float = 0.35              # chromatic aberration, pixels at the corners
    black_point: float = 0.004

    def curve(self) -> np.ndarray:
        x = np.linspace(0.0, 1.0, 1024, dtype=np.float32)
        # Pivoted S curve, gentle: protect highlights, keep detail in the blacks.
        s = 0.5 + (x - 0.5) * self.contrast
        s = np.clip(s, 0.0, 1.0)
        s = x + (s - x) * 0.85
        # soft shoulder
        s = np.where(s > 0.86, 0.86 + (s - 0.86) / (1.0 + (s - 0.86) * 3.2), s)
        s = np.clip((s - self.pivot) * 1.0 + self.pivot, 0.0, 1.0)
        return s.astype(np.float32)


class GrainBank:
    """A small pool of grain tiles, cycled per frame (no temporal freeze)."""

    def __init__(self, size: tuple[int, int] = (720, 405), count: int = 6, seed: int = 2026):
        rng = np.random.default_rng(seed)
        self.tiles = []
        self.cache: dict[tuple[int, int], list[np.ndarray]] = {}
        self.size = size
        for _ in range(count):
            n = rng.normal(0.0, 1.0, (size[1], size[0])).astype(np.float32)
            n = cv2.GaussianBlur(n, (0, 0), 0.6)
            self.tiles.append(n)

    def sample(self, width: int, height: int, index: int) -> np.ndarray:
        key = (width, height)
        if key not in self.cache:
            self.cache[key] = [cv2.resize(t, (width, height), interpolation=cv2.INTER_LINEAR)
                               for t in self.tiles]
        tiles = self.cache[key]
        return tiles[index % len(tiles)]


def _radial_maps(width: int, height: int, cx: float = 0.5, cy: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    x = (xx / width - cx) / 0.5
    y = (yy / height - cy) / 0.5
    r = np.sqrt(x * x + y * y)
    return xx, yy


def apply_grade(img: np.ndarray, grade: Grade, grain_bank: GrainBank | None = None,
                grain_index: int = 0, bloom_scale: float = 1.0) -> np.ndarray:
    h, w = img.shape[:2]
    out = img * grade.exposure
    # white balance
    out = out * np.array([1.0 + grade.temperature, 1.0 + grade.tint * 0.5,
                          1.0 - grade.temperature], dtype=np.float32)
    # per-channel lift / gamma / gain
    lift = np.array(grade.lift, dtype=np.float32)
    gam = np.array(grade.gamma, dtype=np.float32)
    out = np.clip(out, 0.0, 1.0)
    out = out + lift * (1.0 - out)
    if not np.allclose(gam, 1.0):
        out = np.power(np.clip(out, 0.0, 1.0), gam)
    # tone curve on each channel (lookup table, very cheap)
    lut = grade.curve()
    idx = (np.clip(out, 0.0, 1.0) * 1023.0).astype(np.int32)
    out = lut[idx]
    # saturation around luma
    y = luma(out)[..., None]
    out = y + (out - y) * grade.saturation
    # split toning weighted by luma
    yv = np.clip(luma(out), 0.0, 1.0)[..., None]
    ws = np.clip(1.0 - yv * 2.0, 0.0, 1.0) ** 1.4
    wh = np.clip(yv * 2.0 - 0.55, 0.0, 1.0) ** 1.2
    out = out + np.array(grade.shadow_tint, dtype=np.float32) * ws
    out = out + np.array(grade.highlight_tint, dtype=np.float32) * wh
    # black point
    out = np.clip((out - grade.black_point) / (1.0 - grade.black_point), 0.0, 1.0)

    # bloom + halation on a quarter-size copy
    if grade.bloom > 0 or grade.halation > 0:
        small = cv2.resize(out, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
        lum = luma(small)[..., None]
        hl = np.clip(lum - grade.bloom_threshold, 0.0, 1.0) / max(1e-4, 1.0 - grade.bloom_threshold)
        bright = small * hl
        glow = cv2.GaussianBlur(bright, (0, 0), 9.0 * bloom_scale)
        glow = cv2.resize(glow, (w, h), interpolation=cv2.INTER_LINEAR)
        out = out + glow * grade.bloom * 1.6
        if grade.halation > 0:
            red = glow * np.array([1.0, 0.34, 0.18], dtype=np.float32)
            out = out + red * grade.halation * 1.1
    out = np.clip(out, 0.0, 1.0)

    # chromatic aberration (radial, only visible at the edges)
    if grade.ca > 0:
        xx, yy = _radial_maps(w, h)
        dx = (xx - w / 2.0) * (grade.ca / w)
        dy = (yy - h / 2.0) * (grade.ca / w)
        r = cv2.remap(out[..., 0], (xx + dx).astype(np.float32), (yy + dy).astype(np.float32),
                      cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        b = cv2.remap(out[..., 2], (xx - dx).astype(np.float32), (yy - dy).astype(np.float32),
                      cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        out = np.stack([r, out[..., 1], b], axis=-1)

    # vignette
    if grade.vignette > 0:
        xx, yy = _radial_maps(w, h)
        r2 = ((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2)
        mask = 1.0 - grade.vignette * np.clip(r2 * 2.6, 0.0, 1.0) ** 1.35
        out = out * mask[..., None]

    # grain (luma weighted so the blacks stay clean)
    if grain_bank is not None and grade.grain > 0:
        n = grain_bank.sample(w, h, grain_index)
        weight = (0.35 + 0.65 * np.clip(luma(out), 0, 1))[..., None]
        out = out + n[..., None] * grade.grain * weight
    return np.clip(out, 0.0, 1.0)


# --------------------------------------------------------------------------- masks


def circle_mask(width: int, height: int, cx: float, cy: float, r: float, feather: float = 2.0) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) - r
    m = np.clip(-d / max(1e-3, feather), 0.0, 1.0)
    return (m * m * (3 - 2 * m)).astype(np.float32)


def ellipse_mask(width: int, height: int, cx: float, cy: float, ax: float, ay: float,
                 angle_deg: float = 0.0, feather: float = 6.0) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    t = np.deg2rad(angle_deg)
    dx, dy = xx - cx, yy - cy
    u = dx * np.cos(t) + dy * np.sin(t)
    v = -dx * np.sin(t) + dy * np.cos(t)
    d = np.sqrt((u / ax) ** 2 + (v / ay) ** 2) - 1.0
    m = np.clip(-d * min(ax, ay) / max(1e-3, feather), 0.0, 1.0)
    return (m * m * (3 - 2 * m)).astype(np.float32)


# --------------------------------------------------------------------------- depth


def estimate_depth(img: np.ndarray, smooth: int = 61) -> np.ndarray:
    """Cheap depth prior from local detail: sharp = near, smooth = far.

    Used only for slow, small parallax moves on macro shots. It is not a metric
    depth map and is never claimed as one.
    """
    g = luma(img).astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    energy = cv2.GaussianBlur(np.sqrt(gx * gx + gy * gy), (0, 0), 3.0)
    energy = np.log1p(energy * 12.0)
    energy = cv2.GaussianBlur(energy, (0, 0), smooth / 6.0)
    lo, hi = np.percentile(energy, 12), np.percentile(energy, 92)
    d = np.clip((energy - lo) / max(1e-5, hi - lo), 0.0, 1.0)
    return cv2.GaussianBlur(d, (0, 0), smooth / 4.0)


# --------------------------------------------------------------------------- blur


def radial_zoom_blur(img: np.ndarray, strength: float, cx: float, cy: float, samples: int = 7) -> np.ndarray:
    """Motion blur consistent with a zoom: average of scaled copies."""
    if strength <= 1e-4:
        return img
    h, w = img.shape[:2]
    acc = np.zeros_like(img)
    for i in range(samples):
        s = 1.0 + strength * (i / max(1, samples - 1))
        m = cv2.getRotationMatrix2D((cx, cy), 0.0, s)
        acc += cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return acc / samples


def soft_focus(img: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 1e-4:
        return img
    return img * (1 - amount) + cv2.GaussianBlur(img, (0, 0), 2.2) * amount


def screen(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return 1.0 - (1.0 - np.clip(a, 0, 1)) * (1.0 - np.clip(b, 0, 1))


def add_light(img: np.ndarray, light: np.ndarray, gain: float = 1.0) -> np.ndarray:
    return 1.0 - (1.0 - np.clip(img, 0, 1)) * (1.0 - np.clip(light * gain, 0, 1))
