"""Feature measurement on *rendered* endpoint frames.

The morph anchors must be measured on the frames the morph actually blends:
the last frame of shot A and the first frame of shot B, which already include
the camera zoom. Measuring on the source stills would put the circle in the
wrong place as soon as a shot has a push-in.

Each feature is detected with a primary strategy and a fallback, in the 1080x1920
delivery space. `--debug` draws the result so a human can confirm it before the
numbers are trusted.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .morph import Circle

W, H = 1080, 1920


def _gray(img: np.ndarray) -> np.ndarray:
    g = (img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722) * 255.0
    return cv2.medianBlur(g.astype(np.uint8), 7)


def _hsv(img: np.ndarray) -> np.ndarray:
    bgr = cv2.cvtColor((np.clip(img, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)


def _hough(img: np.ndarray, r_min: int, r_max: int, p2: float, rough: tuple[float, float] | None = None):
    g = _gray(img)
    small = cv2.resize(g, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    c = cv2.HoughCircles(small, cv2.HOUGH_GRADIENT, dp=1.4, minDist=max(120, r_min // 2),
                         param1=160, param2=p2, minRadius=max(20, r_min // 2),
                         maxRadius=max(24, r_max // 2))
    if c is None:
        return None
    cand = [(float(x) * 2, float(y) * 2, float(r) * 2) for x, y, r in c[0]]
    if rough is not None:
        cand.sort(key=lambda t: (t[0] - rough[0]) ** 2 + (t[1] - rough[1]) ** 2)
    return cand[0]


def _blob_ellipse(img: np.ndarray, lo, hi, min_area: float, roi=None):
    hsv = _hsv(img)
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
        return None
    cnt = max(cnts, key=cv2.contourArea)
    (cx, cy), (d1, d2), ang = cv2.fitEllipse(cnt)
    return float(cx), float(cy), float(d1 / 2), float(d2 / 2), float(ang)


def _ransac_ellipse(img: np.ndarray, roi, min_axis: float, max_axis: float,
                    iterations: int = 600, tol: float = 0.035, seed: int = 3):
    """Fit an ellipse to the strongest closed edge in a region (RANSAC).

    Robust where blobs and Hough fail: the sunglasses rim, a cropped wheel lip.
    Candidates are scored by inlier count, and rejected if the axes are out of
    the physically plausible range for the feature.
    """
    g = _gray(img)
    edges = cv2.Canny(g, 60, 160)
    mask = np.zeros_like(edges)
    cv2.ellipse(mask, roi[0], roi[1], roi[2], 0, 360, 255, -1)
    edges = cv2.bitwise_and(edges, mask)
    ys, xs = np.nonzero(edges)
    if len(xs) < 200:
        return None
    pts = np.stack([xs, ys], axis=1).astype(np.float32)
    rng = np.random.default_rng(seed)
    best, best_score = None, -1
    sample = min(len(pts), 4000)
    pool = pts[rng.choice(len(pts), sample, replace=False)]
    for _ in range(iterations):
        idx = rng.choice(len(pool), 8, replace=False)
        try:
            (cx, cy), (d1, d2), ang = cv2.fitEllipse(pool[idx].reshape(-1, 1, 2))
        except cv2.error:
            continue
        a, b = d1 / 2, d2 / 2
        if not (min_axis <= min(a, b) and max(a, b) <= max_axis):
            continue
        t = np.deg2rad(ang)
        dx, dy = pool[:, 0] - cx, pool[:, 1] - cy
        u = dx * np.cos(t) + dy * np.sin(t)
        v = -dx * np.sin(t) + dy * np.cos(t)
        rho = np.sqrt((u / a) ** 2 + (v / b) ** 2)
        inl = np.abs(rho - 1.0) < tol
        score = float(inl.sum())
        if score > best_score:
            best_score = score
            best = (cx, cy, a, b, ang, inl)
    if best is None:
        return None
    cx, cy, a, b, ang, inl = best
    refit = pool[inl]
    if len(refit) >= 20:
        (cx, cy), (d1, d2), ang = cv2.fitEllipse(refit.reshape(-1, 1, 2))
        a, b = d1 / 2, d2 / 2
    return float(cx), float(cy), float(a), float(b), float(ang), int(best_score)


def _ring(img: np.ndarray, cx: float, cy: float, r_min: float, r_max: float,
          samples: int = 720) -> tuple[float, float, float] | None:
    """Ray-cast the brightest sample: reliable on the chrome lip."""
    v = _hsv(img)[..., 2].astype(np.float32)
    v = cv2.GaussianBlur(v, (0, 0), 1.5)
    rs = np.arange(r_min, r_max, 1.0, dtype=np.float32)
    angs = np.linspace(0, 2 * np.pi, samples, endpoint=False, dtype=np.float32)
    xs = cx + np.cos(angs)[:, None] * rs[None, :]
    ys = cy + np.sin(angs)[:, None] * rs[None, :]
    vals = cv2.remap(v, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    idx = np.argmax(vals, axis=1)
    radii = rs[idx]
    radii = radii[(radii > r_min) & (radii < r_max - 1)]
    if len(radii) < 30:
        return None
    r = float(np.median(radii))
    keep = np.abs(radii - r) < 0.08 * r
    return cx, cy, float(np.median(radii[keep])) if keep.sum() > 20 else r


# --------------------------------------------------------------------------- features


def rim(img: np.ndarray) -> Circle:
    """Bright chrome lip of the wheel, centred on the hub cap.

    The hub is a dark ellipse at the mechanical centre of the wheel: far more
    reliable than a Hough circle, which locks onto the visible bottom arc when
    the lip is partly cropped. The lip radius is then the median ray distance.
    """
    hub = _blob_ellipse(img, (0, 0, 0), (180, 90, 80), 6000,
                        roi=((540, 980), (460, 460), 0))
    if hub is None:
        hub = _blob_ellipse(img, (0, 0, 0), (180, 90, 90), 3000)
    if hub is not None:
        cx, cy = hub[0], hub[1]
    else:
        hough = _hough(img, 120, 220, p2=60, rough=(540, 980))
        cx, cy = (hough[0], hough[1]) if hough else (540.0, 980.0)
    ring = _ring(img, cx, cy, 380.0, 820.0, samples=900)
    if ring is not None:
        return Circle(cx, cy, ring[2])
    hough = _hough(img, 520, 780, p2=70, rough=(cx, cy))
    return Circle(cx, cy, hough[2] if hough else 600.0)


def plate(img: np.ndarray) -> Circle:
    """Rim of the white porcelain plate (bright ellipse on the table)."""
    blob = _blob_ellipse(img, (0, 0, 140), (80, 120, 255), 250000)
    if blob:
        cx, cy, a, b, _ = blob
        return Circle(cx, cy, (a + b) / 2)
    ell = _ransac_ellipse(img, ((540, 1050), (620, 620), 0), 380, 760)
    if ell:
        return Circle(ell[0], ell[1], (ell[2] + ell[3]) / 2)
    hough = _hough(img, 480, 700, p2=75, rough=(540, 1050))
    return Circle(*hough) if hough else Circle(520, 1050, 560)


def cup(img: np.ndarray) -> Circle:
    """Crema surface inside the cup (warm blob)."""
    blob = _blob_ellipse(img, (4, 80, 30), (34, 255, 240), 40000,
                         roi=((540, 1190), (420, 420), 0))
    if blob:
        cx, cy, a, b, _ = blob
        return Circle(cx, cy, (a + b) / 2)
    hough = _hough(img, 250, 360, p2=70, rough=(540, 1190))
    return Circle(*hough) if hough else Circle(540, 1190, 300)


def dome(img: np.ndarray) -> Circle:
    """Dark chocolate sphere (macro shot)."""
    blob = _blob_ellipse(img, (0, 55, 15), (32, 255, 100), 80000,
                         roi=((560, 1330), (470, 470), 0))
    if blob:
        cx, cy, a, b, _ = blob
        return Circle(cx, cy, (a + b) / 2)
    return Circle(560, 1330, 390)


def lens(img: np.ndarray) -> tuple[float, float, float, float, float]:
    """Interior of the sunglasses lens: (cx, cy, ax, ay, angle).

    Fitted with RANSAC on the rim edges: the reflection inside the lens is
    bright at the top and dark at the bottom, so a chroma blob only captures
    half of it and would put the aperture off-centre.
    """
    ell = _ransac_ellipse(img, ((700, 1000), (700, 800), 0), 260, 640,
                          iterations=900, tol=0.030, seed=11)
    if ell:
        cx, cy, a, b, ang, inliers = ell
        return cx, cy, a * 0.985, b * 0.985, ang
    blob = _blob_ellipse(img, (0, 0, 70), (60, 120, 255), 200000)
    if blob:
        cx, cy, a, b, ang = blob
        return cx, cy, a * 0.99, b * 0.99, ang
    return 660.0, 1010.0, 470.0, 660.0, 6.0


CIRCLES = {"rim": rim, "plate": plate, "cup": cup, "dome": dome}
ELLIPSES = {"lens": lens}


def measure(img: np.ndarray, name: str):
    if name in CIRCLES:
        return CIRCLES[name](img)
    if name in ELLIPSES:
        return ELLIPSES[name](img)
    raise KeyError(name)


def draw(img: np.ndarray, name: str, geo) -> np.ndarray:
    out = (np.clip(img, 0, 1) * 255).astype(np.uint8).copy()
    out = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
    if isinstance(geo, Circle):
        cv2.circle(out, (int(geo.cx), int(geo.cy)), int(geo.r), (90, 240, 150), 4)
        cv2.drawMarker(out, (int(geo.cx), int(geo.cy)), (90, 240, 150), cv2.MARKER_CROSS, 70, 4)
    else:
        cx, cy, ax, ay, ang = geo
        cv2.ellipse(out, (int(cx), int(cy)), (int(ax), int(ay)), ang, 0, 360, (90, 240, 150), 4)
        cv2.drawMarker(out, (int(cx), int(cy)), (90, 240, 150), cv2.MARKER_CROSS, 70, 4)
    cv2.putText(out, name, (24, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (90, 240, 150), 3)
    return out


# --------------------------------------------------------------------------- optimiser


def _edge_map(img: np.ndarray) -> np.ndarray:
    g = _gray(img).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 1.2)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.GaussianBlur(np.abs(gx) + np.abs(gy), (0, 0), 1.0)


def _score_circle(edge: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Median edge response along circles (robust to occlusion and speculars)."""
    h, w = edge.shape
    xsi = np.clip(xs, 0, w - 1.001)
    ysi = np.clip(ys, 0, h - 1.001)
    x0 = xsi.astype(np.int32)
    y0 = ysi.astype(np.int32)
    fx = xsi - x0
    fy = ysi - y0
    v = (edge[y0, x0] * (1 - fx) * (1 - fy) + edge[y0, x0 + 1] * fx * (1 - fy) +
         edge[y0 + 1, x0] * (1 - fx) * fy + edge[y0 + 1, x0 + 1] * fx * fy)
    return np.median(v, axis=-1)


def refine_circle(img: np.ndarray, guess: tuple[float, float, float],
                  dc: float = 90.0, dr: float = 0.12, samples: int = 360,
                  steps: int = 3) -> tuple[float, float, float]:
    """Local search of the best circular edge around a measured guess.

    Maximises the median gradient along the circle: the objective is flat for a
    wrong circle (most samples miss the edge) and peaks sharply on the real
    boundary, which is exactly the behaviour wanted for a morph anchor.
    """
    edge = _edge_map(img)
    angs = np.linspace(0, 2 * np.pi, samples, endpoint=False, dtype=np.float32)
    ca, sa = np.cos(angs), np.sin(angs)
    cx, cy, r = guess
    for step in range(steps):
        span_c = dc / (2 ** step)
        span_r = dr / (2 ** step)
        best = (-1.0, cx, cy, r)
        for ddx in np.linspace(-span_c, span_c, 9):
            for ddy in np.linspace(-span_c, span_c, 9):
                for kr in np.linspace(1 - span_r, 1 + span_r, 9):
                    rr = r * kr
                    xs = (cx + ddx) + ca * rr
                    ys = (cy + ddy) + sa * rr
                    s = float(np.mean(_score_circle(edge, xs[None, :], ys[None, :])))
                    if s > best[0]:
                        best = (s, cx + ddx, cy + ddy, rr)
        _, cx, cy, r = best
    return float(cx), float(cy), float(r)


def fit(name: str, frame: np.ndarray, guess: tuple[float, float, float],
        dc: float = 90.0, dr: float = 0.12) -> Circle:
    cx, cy, r = refine_circle(frame, guess, dc=dc, dr=dr)
    return Circle(cx, cy, r)


def _score_ellipse(edge: np.ndarray, cx: float, cy: float, ax: float, ay: float,
                   ang: float, samples: int = 360) -> float:
    t = np.linspace(0, 2 * np.pi, samples, endpoint=False)
    c, s = np.cos(np.deg2rad(ang)), np.sin(np.deg2rad(ang))
    u, v = ax * np.cos(t), ay * np.sin(t)
    xs = cx + u * c - v * s
    ys = cy + u * s + v * c
    return float(np.median(_score_circle(edge, xs[None, :], ys[None, :])))


def refine_ellipse(img: np.ndarray, guess: tuple[float, float, float, float, float],
                   dc: float = 40.0, da: float = 0.06, da_ang: float = 5.0,
                   rounds: int = 3) -> tuple[float, float, float, float, float]:
    """Coordinate descent on (cx, cy, ax, ay, angle), median gradient objective."""
    edge = _edge_map(img)
    cx, cy, ax, ay, ang = guess
    for step in range(rounds):
        sc, sa, sang = dc / (2 ** step), da / (2 ** step), da_ang / (2 ** step)
        for _ in range(2):
            cx = max((_score_ellipse(edge, cx + d, cy, ax, ay, ang), cx + d)
                     for d in np.linspace(-sc, sc, 7))[1]
            cy = max((_score_ellipse(edge, cx, cy + d, ax, ay, ang), cy + d)
                     for d in np.linspace(-sc, sc, 7))[1]
            ax = max((_score_ellipse(edge, cx, cy, ax * k, ay, ang), ax * k)
                     for k in np.linspace(1 - sa, 1 + sa, 7))[1]
            ay = max((_score_ellipse(edge, cx, cy, ax, ay * k, ang), ay * k)
                     for k in np.linspace(1 - sa, 1 + sa, 7))[1]
            ang = max((_score_ellipse(edge, cx, cy, ax, ay, ang + d), ang + d)
                      for d in np.linspace(-sang, sang, 7))[1]
    return float(cx), float(cy), float(ax), float(ay), float(ang)
