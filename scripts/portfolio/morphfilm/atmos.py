"""Atmosphere: steam, dust, flares, moving specular sweeps.

Generated stills are frozen light. These layers put the *light* back in motion,
which is what makes a still plate read as a filmed shot. Everything is
procedural and deterministic (seeded), so a re-render is bit-comparable.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import imageops


class NoiseBank:
    """Scrolling multi-octave value noise, sampled at a reduced resolution."""

    def __init__(self, height: int, width: int, octaves: int = 4, seed: int = 7):
        rng = np.random.default_rng(seed)
        self.layers = []
        for i in range(octaves):
            h = max(16, height >> (2 + i))
            w = max(16, width >> (2 + i))
            base = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
            base = cv2.GaussianBlur(base, (0, 0), 1.2)
            base = (base - base.min()) / max(1e-6, float(base.max() - base.min()))
            self.layers.append(base)

    def sample(self, t: float, speed: float, scale: float = 1.0, wobble: float = 0.0,
               out: tuple[int, int] = (1080, 1920)) -> np.ndarray:
        W, H = out
        acc = np.zeros((H, W), dtype=np.float32)
        amp = 1.0
        norm = 0.0
        for i, layer in enumerate(self.layers):
            h, w = layer.shape
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            dy = (t * speed * (0.6 + 0.5 * i) * h * 0.06) % h
            dx = wobble * w * 0.06 * np.sin(t * 0.7 + i * 1.3)
            sx = xx + dx
            sy = yy + dy
            l = cv2.remap(layer, sx.astype(np.float32), sy.astype(np.float32),
                          cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
            l = cv2.resize(l, (W, H), interpolation=cv2.INTER_LINEAR)
            acc += l * amp
            norm += amp
            amp *= 0.55
        return acc / max(1e-6, norm)


class Steam:
    """Warm vapour rising from a plate, masked to a cone above the subject."""

    def __init__(self, seed: int = 31, warm: float = 1.0):
        self.bank = NoiseBank(1920, 1080, octaves=4, seed=seed)
        self.warm = warm

    def render(self, t: float, cx: float, cy: float, width: float, height: float,
               strength: float = 0.10) -> np.ndarray:
        W, H = 1080, 1920
        n = self.bank.sample(t, speed=1.0, wobble=1.6)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        # cone widening upward from the plate
        rel = (yy - cy) / max(1.0, height)
        spread = width * (0.22 + 0.55 * np.clip(-rel, 0.0, 1.0))
        inside = np.exp(-((xx - cx) / np.maximum(24.0, spread)) ** 2)
        rise = np.clip(1.0 - (cy - yy) / max(1.0, height * 1.55), 0.0, 1.0)
        rise = np.where(yy < cy, rise ** 1.3, 0.0)
        density = np.clip(n * 1.55 - 0.62, 0.0, 1.0) * inside * rise
        density = cv2.GaussianBlur(density, (0, 0), 6.0)
        colour = np.array([1.0, 0.92, 0.80], dtype=np.float32) if self.warm > 0 else np.array(
            [0.9, 0.95, 1.0], dtype=np.float32)
        return density[..., None] * colour * strength


class Dust:
    """Sparse drifting bright specks, only in the light."""

    def __init__(self, count: int = 90, seed: int = 11, colour=(1.0, 0.88, 0.7)):
        rng = np.random.default_rng(seed)
        self.x = rng.uniform(0, 1, count).astype(np.float32)
        self.y = rng.uniform(0, 1, count).astype(np.float32)
        self.z = rng.uniform(0.2, 1.0, count).astype(np.float32)
        self.v = rng.uniform(0.004, 0.02, count).astype(np.float32)
        self.wob = rng.uniform(0, 6.28, count).astype(np.float32)
        self.colour = np.array(colour, dtype=np.float32)

    def render(self, t: float, strength: float = 0.5, blur: float = 1.0) -> np.ndarray:
        H, W = 1920 // 4, 1080 // 4
        canvas = np.zeros((H, W), dtype=np.float32)
        for i in range(len(self.x)):
            x = (self.x[i] + 0.01 * np.sin(t * 0.6 + self.wob[i])) % 1.0
            y = (self.y[i] - self.v[i] * t) % 1.0
            px, py = int(x * (W - 1)), int(y * (H - 1))
            cv2.circle(canvas, (px, py), max(1, int(1.4 * self.z[i])), float(self.z[i]), -1)
        canvas = cv2.GaussianBlur(canvas, (0, 0), max(0.4, blur))
        up = cv2.resize(canvas, (1080, 1920), interpolation=cv2.INTER_LINEAR)
        return up[..., None] * self.colour * strength


def flare(centre: tuple[float, float], strength: float, radius: float = 520.0,
          tint: tuple[float, float, float] = (1.0, 0.78, 0.5), rings: float = 0.25) -> np.ndarray:
    H, W = 1920, 1080
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = centre
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / radius
    core = np.exp(-(r ** 2) * 3.0)
    halo = np.exp(-r * 1.6) * 0.35
    ring = (np.exp(-((r - 0.75) ** 2) * 90.0) * rings)
    streak = np.exp(-((yy - cy) ** 2) / (2 * 18.0 ** 2)) * np.exp(-np.abs(xx - cx) / (W * 0.25)) * 0.5
    light = (core + halo + ring) + streak
    return light[..., None] * np.array(tint, dtype=np.float32) * strength


def specular_sweep(img: np.ndarray, t: float, angle_deg: float = 18.0, speed: float = 0.55,
                   strength: float = 0.30, width: float = 0.20, threshold: float = 0.42) -> np.ndarray:
    """A soft band of light travelling across glossy highlights only.

    Applied where the plate is already bright, so it reads as a moving
    reflection rather than as a painted band.
    """
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t_rad = np.deg2rad(angle_deg)
    u = (xx * np.cos(t_rad) + yy * np.sin(t_rad)) / W
    pos = -0.35 + ((t * speed) % 1.0) * 1.7
    band = np.exp(-((u - pos) ** 2) / (2 * width ** 2))
    lum = imageops.luma(img)
    hi = np.clip((lum - threshold) / max(1e-3, 1.0 - threshold), 0.0, 1.0) ** 1.5
    light = (band * hi)[..., None] * np.array([1.0, 0.93, 0.82], dtype=np.float32) * strength
    return imageops.add_light(img, light)


def tinted_light_leak(t: float, strength: float = 0.14) -> np.ndarray:
    H, W = 1920, 1080
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    x = xx / W + 0.12 * np.sin(t * 0.5)
    y = yy / H
    g = np.exp(-((x - 0.72) ** 2) / 0.16) * np.exp(-((y - 0.18) ** 2) / 0.10)
    return g[..., None] * np.array([1.0, 0.62, 0.32], dtype=np.float32) * strength


def vignette_pulse(img: np.ndarray, amount: float = 0.06, phase: float = 0.0) -> np.ndarray:
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r2 = ((xx / W - 0.5) ** 2 + (yy / H - 0.5) ** 2) * 2.4
    k = 1.0 - amount * (0.5 + 0.5 * np.sin(phase)) * np.clip(r2, 0, 1) ** 1.4
    return img * k[..., None]
