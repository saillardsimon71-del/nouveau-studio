"""Derived plates: deterministic variants made from the master stills.

Two reasons to derive instead of regenerate:

* the automotive film must not reuse the exact same wheel frame as the food
  film, so the wheel is re-framed (rotation + tighter crop) and cooled;
* a derived master keeps the same photographic quality and costs nothing.

Every derivation is recorded (operation + parameters) in the production JSON, so
the delivery is reproducible and honest about what was transformed.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


def _read(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return img


def _write(img: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.clip(img, 0, 255).astype(np.uint8))


def _rotate_cover(img: np.ndarray, angle: float, zoom: float = 1.0) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, zoom)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LANCZOS4,
                          borderMode=cv2.BORDER_REPLICATE)


def _crop(img: np.ndarray, scale: float, dx: float = 0.0, dy: float = 0.0) -> np.ndarray:
    h, w = img.shape[:2]
    nh, nw = int(h * scale), int(w * scale)
    x = int((w - nw) / 2 + dx * w)
    y = int((h - nh) / 2 + dy * h)
    x, y = max(0, min(w - nw, x)), max(0, min(h - nh, y))
    return img[y:y + nh, x:x + nw]


def _resize(img: np.ndarray, w: int, h: int) -> np.ndarray:
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_LANCZOS4)


def _cool(img: np.ndarray, strength: float = 1.0) -> np.ndarray:
    f = img.astype(np.float32) / 255.0
    f[..., 0] *= 1.0 + 0.05 * strength      # B
    f[..., 1] *= 1.0 - 0.01 * strength
    f[..., 2] *= 1.0 - 0.06 * strength      # R
    f = np.clip(f, 0, 1)
    f = np.clip((f - 0.5) * (1.0 + 0.06 * strength) + 0.5, 0, 1)
    return f * 255.0


def derive(root: Path) -> dict:
    """Create the two derived plates. Idempotent, returns the operations log."""
    log: dict = {}
    src_wheel = root / "food" / "f1-rim.png"
    if src_wheel.is_file():
        out = root / "auto" / "a3-wheel.png"
        img = _read(src_wheel)
        # No rotation: the source wheel is not centred, and rotating it produced
        # mirrored tiles (reflection border). A re-crop is enough to make a
        # distinct framing while keeping the photographic quality intact.
        img = _crop(img, 0.84, 0.05, -0.01)
        img = _resize(img, 768, 1376)
        img = _cool(img, 1.0)
        _write(img, out)
        log["auto/a3-wheel.png"] = {
            "source": "food/f1-rim.png",
            "operations": ["crop 84% + shift (re-framed)", "resize 768x1376", "cool grade"],
        }
    return log


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data/portfolio-2026-10-23"))
    args = ap.parse_args()
    print(json.dumps(derive(args.root), indent=2, ensure_ascii=False))
