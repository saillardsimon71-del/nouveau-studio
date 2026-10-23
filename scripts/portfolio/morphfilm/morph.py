"""Morph transitions.

Five operators, each chosen for what a given pair of shots actually shares:

``flow``    optical-flow warp. The default: real pixel displacement, forward and
            backward, with an occlusion test so the two halves never ghost.
``radial``  circle-aligned morph (a wheel rim into a porcelain plate). The whole
            transform is expressed in polar coordinates around the detected
            circle, so the spokes twist into the coulis spiral while the radius
            interpolates. This is the "wow" transition of the food film.
``portal``  a lens-shaped aperture opens inside a pair of sunglasses and the
            reflection becomes the real scene, with a refracting rim.
``bloom``   an exposure/flare morph: the light of one shot becomes the light of
            the next. Used where both images share a strong highlight.
``zoom``    a zoom-through on a shared circular feature (cup -> chocolate dome).

Every operator is exact at both ends: ``w == 0`` returns A untouched and
``w == 1`` returns B untouched. That matters: a morph that does not land
perfectly on the next shot reads as a glitch, not as a transition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import imageops


# --------------------------------------------------------------------------- flow


def _gray(img: np.ndarray, scale: float) -> np.ndarray:
    g = imageops.luma(img)
    h, w = g.shape
    g = cv2.resize(g, (max(8, int(w * scale)), max(8, int(h * scale))), interpolation=cv2.INTER_AREA)
    return np.clip(g * 255.0, 0, 255).astype(np.uint8)


def optical_flow(a: np.ndarray, b: np.ndarray, scale: float = 0.5, iterations: int = 4) -> dict:
    """DIS optical flow both ways + forward/backward occlusion masks."""
    ga, gb = _gray(a, scale), _gray(b, scale)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    dis.setFinestScale(1)
    dis.setPatchSize(8)
    dis.setPatchStride(4)
    dis.setUseSpatialPropagation(True)
    fab = dis.calc(ga, gb, None)
    fba = dis.calc(gb, ga, None)
    h, w = a.shape[:2]
    up = lambda f: cv2.resize(f, (w, h), interpolation=cv2.INTER_LINEAR) / scale
    fab, fba = up(fab), up(fba)
    # forward/backward consistency
    xx, yy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    wa = cv2.remap(fba, (xx + fab[..., 0]).astype(np.float32), (yy + fab[..., 1]).astype(np.float32),
                   cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    err = np.sqrt((fab[..., 0] + wa[..., 0]) ** 2 + (fab[..., 1] + wa[..., 1]) ** 2)
    occ_a = cv2.GaussianBlur(np.clip((err - 1.6) / 6.4, 0.0, 1.0), (0, 0), 2.0)
    wb = cv2.remap(fab, (xx + fba[..., 0]).astype(np.float32), (yy + fba[..., 1]).astype(np.float32),
                   cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    errb = np.sqrt((fba[..., 0] + wb[..., 0]) ** 2 + (fba[..., 1] + wb[..., 1]) ** 2)
    occ_b = cv2.GaussianBlur(np.clip((errb - 1.6) / 6.4, 0.0, 1.0), (0, 0), 2.0)
    return {"fab": fab, "fba": fba, "occ_a": occ_a, "occ_b": occ_b,
            "xx": xx, "yy": yy}


def _remap(img: np.ndarray, mx: np.ndarray, my: np.ndarray) -> np.ndarray:
    return cv2.remap(img, np.asarray(mx, dtype=np.float32), np.asarray(my, dtype=np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def flow_morph(a: np.ndarray, b: np.ndarray, w: float, flow: dict,
               liquid: float = 0.0) -> np.ndarray:
    """Sample A forward and B backward along the flow, weighted by w."""
    xx, yy = flow["xx"], flow["yy"]
    fab, fba = flow["fab"], flow["fba"]
    # displacement magnitude control: 0 at the ends, full in the middle
    k = w
    mx_a = xx - k * fab[..., 0]
    my_a = yy - k * fab[..., 1]
    mx_b = xx + (1.0 - k) * fba[..., 0]
    my_b = yy + (1.0 - k) * fba[..., 1]
    if liquid > 0:
        # a gentle non-rigid swell in the middle of the morph
        s = np.sin(np.pi * w) ** 2 * liquid
        h, wd = xx.shape
        cxn, cyn = wd / 2.0, h / 2.0
        r = np.sqrt((xx - cxn) ** 2 + (yy - cyn) ** 2) / (h * 0.7)
        swell = 1.0 + s * (0.06 * np.cos(r * 9.0))
        mx_a = cxn + (mx_a - cxn) * swell
        my_a = cyn + (my_a - cyn) * swell
        mx_b = cxn + (mx_b - cxn) * swell
        my_b = cyn + (my_b - cyn) * swell
    fa = _remap(a, mx_a, my_a)
    fb = _remap(b, mx_b, my_b)
    wa = (1.0 - w) * (1.0 - 0.65 * flow["occ_b"] * w)
    wb = w * (1.0 - 0.65 * flow["occ_a"] * (1.0 - w))
    s = wa + wb
    out = (fa * (wa / s)[..., None] + fb * (wb / s)[..., None])
    if liquid > 0:
        # a soft radial swell hides the residual double-exposure in the middle
        k = np.sin(np.pi * w) ** 2
        out = imageops.radial_zoom_blur(out, 0.035 * liquid * k * 40, xx.shape[1] / 2,
                                       xx.shape[0] / 2, samples=3)
    return out


# --------------------------------------------------------------------------- radial


@dataclass
class Circle:
    cx: float
    cy: float
    r: float


def radial_morph(a: np.ndarray, b: np.ndarray, w: float, ca: Circle, cb: Circle,
                 twist_deg: float = 34.0, spiral: float = 0.55,
                 inside: float = 1.02, feather: float = 26.0) -> np.ndarray:
    """Circle-aligned polar morph: radius, angle, spiral and centre all interpolate.

    Inside the disc, each frame is remapped so that A's circle matches the
    intermediate circle and B's circle matches the same one. The angle offset
    grows with the normalised radius, so radial spokes become a spiral exactly
    when the two are blended: that is what makes a wheel turn into a plated
    dessert instead of a cross-dissolve. Outside the disc the two frames
    cross-fade, which is the only honest option: there is no shared geometry.

    At ``w=1`` every offset is zero, so the result is exactly B inside the disc.
    """
    h, wd = a.shape[:2]
    xx, yy = np.meshgrid(np.arange(wd, dtype=np.float32), np.arange(h, dtype=np.float32))
    cx = ca.cx + (cb.cx - ca.cx) * w
    cy = ca.cy + (cb.cy - ca.cy) * w
    r = ca.r + (cb.r - ca.r) * w
    dx, dy = xx - cx, yy - cy
    radius = np.sqrt(dx * dx + dy * dy)
    rn = radius / max(1e-3, r)
    base = np.arctan2(dy, dx)
    sm = np.clip(rn, 0.0, 1.6)
    # A twists forward and unwinds as B arrives; B unwinds back symmetrically.
    ang_a = np.deg2rad(twist_deg) * (1.0 - w) * sm + spiral * sm * w
    ang_b = -np.deg2rad(twist_deg) * w * sm - spiral * sm * (1.0 - w)
    sa = ca.r / max(1e-3, r)
    sb = cb.r / max(1e-3, r)

    def sample(img, center, scale, ang):
        mx = center[0] + np.cos(base + ang) * radius * scale
        my = center[1] + np.sin(base + ang) * radius * scale
        return _remap(img, mx, my)

    fa = sample(a, (ca.cx, ca.cy), sa, ang_a)
    fb = sample(b, (cb.cx, cb.cy), sb, ang_b)
    # angular smear peaks mid-morph: motion blur that reads as speed, not mush
    smear = np.sin(np.pi * w) ** 1.5 * 0.55
    if smear > 0.02:
        fa = _angular_smear(fa, cx, cy, smear)
    mask = imageops.circle_mask(wd, h, cx, cy, r * inside, feather=feather)[..., None]
    out = fa * (1 - w) + fb * w
    # luminance match inside the disc so the crossing point does not flash
    la = float(np.mean(imageops.luma(a) * imageops.circle_mask(wd, h, ca.cx, ca.cy, ca.r * 1.02)))
    lb = float(np.mean(imageops.luma(b) * imageops.circle_mask(wd, h, cb.cx, cb.cy, cb.r * 1.02)))
    gain = 1.0 + (lb - la) * 0.35 * np.sin(np.pi * w)
    out = out * gain
    return {"inside": np.clip(out, 0, 1), "mask": mask}


def _angular_smear(img: np.ndarray, cx: float, cy: float, amount: float,
                   samples: int = 7, deg: float = 2.6) -> np.ndarray:
    """Rotational motion blur around (cx, cy), strongest at the edge."""
    h, w = img.shape[:2]
    acc = img.astype(np.float32).copy()
    for i in range(1, samples):
        k = (i / (samples - 1)) * amount
        m = cv2.getRotationMatrix2D((cx, cy), deg * k * (1 if i % 2 else -1), 1.0)
        acc += cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)
    return acc / (samples)


# --------------------------------------------------------------------------- portal


def portal_morph(a: np.ndarray, b: np.ndarray, w: float, cx: float, cy: float,
                 ax: float, ay: float, angle: float, grow: tuple[float, float] = (0.62, 3.1),
                 rim: float = 1.0) -> np.ndarray:
    """A lens-shaped aperture opens on a reflection and becomes the real scene.

    The aperture grows past the glass edge, so it never has to clip against a
    hard rim: the sunglasses frame simply leaves the frame as the scene takes
    over. The refracting rim is a thin gradient of the mask, and the incoming
    plate is pre-scaled so the lens interior is fully covered at every step.
    """
    h, wd = a.shape[:2]
    if w >= 0.999:
        return b.copy()
    if w <= 0.0:
        return a.copy()
    s = grow[0] + (grow[1] - grow[0]) * (w ** 0.85)
    # full coverage: the incoming shot is scaled to the aperture opening
    cover = min(1.9, max(1.0, (ax * s) / 470.0, (ay * s) / 760.0))
    zoom_b = (1.02 + 0.05 * (1.0 - w) ** 2) * cover
    m = cv2.getRotationMatrix2D((cx, cy), 0.0, zoom_b)
    fb = cv2.warpAffine(b, m, (wd, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    feather = max(3.0, 34.0 * s * 0.25)
    mask = imageops.ellipse_mask(wd, h, cx, cy, ax * s, ay * s, angle, feather=feather)
    m3 = mask[..., None]
    a_dim = a * (1.0 - 0.22 * w * (1.0 - mask))[..., None]
    out = a_dim * (1 - m3) + fb * m3
    # refracting rim: gradient of the mask, warm on the light side
    edge = np.clip(mask - cv2.GaussianBlur(mask, (0, 0), 7.0), 0.0, 1.0) * 2.2
    edge = cv2.GaussianBlur(edge, (0, 0), 2.0)[..., None]
    warm = np.array([1.0, 0.86, 0.66], dtype=np.float32)
    out = imageops.add_light(out, edge * warm * (0.55 * rim))
    out[..., 0] = np.clip(out[..., 0] + edge[..., 0] * 0.06, 0, 1)
    return np.clip(out, 0.0, 1.0)


# --------------------------------------------------------------------------- bloom


def bloom_morph(a: np.ndarray, b: np.ndarray, w: float, cx: float, cy: float,
                warm: tuple[float, float, float] = (1.0, 0.72, 0.38),
                streak: float = 1.0) -> np.ndarray:
    """The highlight of A swells into the exposure of B."""
    h, wd = a.shape[:2]
    xx, yy = np.meshgrid(np.arange(wd, dtype=np.float32), np.arange(h, dtype=np.float32))
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (np.hypot(wd, h) * 0.55)
    if w < 0.5:
        k = (w / 0.5) ** 1.4
        img = imageops.radial_zoom_blur(a, 0.20 * k, cx, cy, samples=6)
        glow = np.exp(-(r ** 2) * 3.2)[..., None] * np.array(warm, dtype=np.float32)
        img = imageops.add_light(img, glow * (0.85 * k))
        img = img * (1.0 + 0.35 * k)
    else:
        k = ((w - 0.5) / 0.5) ** 0.8
        # B arrives out of focus and settles: a defocus rack reads as an
        # exposure change, while a radial zoom blur would copy the plate rim at
        # every sample and print concentric ghost rings across it.
        img = imageops.soft_focus(b, 0.85 * (1 - k))
        settle = 1.055 - 0.055 * k
        m = cv2.getRotationMatrix2D((cx, cy), 0.0, settle)
        img = cv2.warpAffine(img, m, (wd, h), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REFLECT)
        glow = np.exp(-(r ** 2) * 4.5)[..., None] * np.array(warm, dtype=np.float32)
        img = imageops.add_light(img, glow * (0.70 * (1 - k)))
        img = img * (0.60 + 0.40 * k)
    # anamorphic streak through the flare centre
    g = np.exp(-((yy - cy) ** 2) / (2 * 26.0 ** 2)) * np.exp(-((xx - cx) ** 2) / (2 * (wd * 0.55) ** 2))
    s = g[..., None] * np.array([1.0, 0.80, 0.55], dtype=np.float32) * (0.35 * np.sin(np.pi * w) * streak)
    img = imageops.add_light(img, s)
    return np.clip(img, 0.0, 1.0)


# --------------------------------------------------------------------------- zoom through


def _zoom_at(img: np.ndarray, cx: float, cy: float, z: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((cx, cy), 0.0, z)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def zoom_through(a: np.ndarray, b: np.ndarray, w: float, cx: float, cy: float,
                 depth: float = 2.3) -> np.ndarray:
    """Fall into a circular subject, come out of the next one."""
    h, wd = a.shape[:2]
    if w < 0.52:
        k = (w / 0.52)
        za = 1.0 + (depth - 1.0) * (k ** 1.6)
        m = cv2.getRotationMatrix2D((cx, cy), 0.0, za)
        img = cv2.warpAffine(a, m, (wd, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        img = imageops.radial_zoom_blur(img, 0.30 * (k ** 2.2), cx, cy, samples=8)
        img = img * (1.0 - 0.55 * (k ** 3))
        return np.clip(img, 0, 1)
    k = ((w - 0.52) / 0.48)
    zb = depth * (1 - k) + 1.0 * k
    m = cv2.getRotationMatrix2D((cx, cy), 0.0, zb)
    img = cv2.warpAffine(b, m, (wd, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    img = imageops.radial_zoom_blur(img, 0.26 * ((1 - k) ** 2.0), cx, cy, samples=8)
    img = img * (0.45 + 0.55 * (k ** 0.7))
    return np.clip(img, 0, 1)


# --------------------------------------------------------------------------- spin


def _spin_sample(img: np.ndarray, cx: float, cy: float, zoom: float, deg: float,
                 blur: float, samples: int = 9) -> np.ndarray:
    """Rotate + scale around a point, with motion blur proportional to the move."""
    h, w = img.shape[:2]
    if blur <= 0.02:
        m = cv2.getRotationMatrix2D((cx, cy), deg, zoom)
        return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REFLECT)
    acc = np.zeros_like(img, dtype=np.float32)
    for i in range(samples):
        k = (i / (samples - 1)) - 0.5
        m = cv2.getRotationMatrix2D((cx, cy), deg * (1 + 0.10 * k * blur), zoom * (1 + 0.035 * k * blur))
        acc += cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return acc / samples


def spin_through(a: np.ndarray, b: np.ndarray, w: float, ca: Circle, cb: Circle,
                 spin: float = 42.0, zoom: float = 1.55, flash: float = 0.55,
                 warm: tuple[float, float, float] = (1.0, 0.78, 0.52)) -> np.ndarray:
    """Whip morph: the circle spins and pushes, then resolves into the next circle.

    This is the transition that actually works for two photographs with no shared
    geometry: instead of blending them (which ghosts), the outgoing shape is
    spun and pushed through the lens, the incoming shape arrives still spinning
    and settles. Motion is continuous across the cut, and only one source is
    visible at any time, so nothing double-exposes.

    ``flash`` lifts the exposure at the crossover, which hides the single frame
    where the two motions meet and reads as a specular flare.
    """
    h, wd = a.shape[:2]
    if w < 0.5:
        k = w / 0.5
        e = k ** 1.7
        img = _spin_sample(a, ca.cx, ca.cy, 1.0 + (zoom - 1.0) * e, spin * e,
                           blur=0.35 + 1.15 * e)
        img = imageops.radial_zoom_blur(img, 0.16 * e ** 2.2, ca.cx, ca.cy, samples=5)
        img = img * (1.0 - 0.30 * e ** 2.6)
        cx, cy = ca.cx, ca.cy
    else:
        k = (w - 0.5) / 0.5
        e = (1.0 - k) ** 1.7
        img = _spin_sample(b, cb.cx, cb.cy, 1.0 + (zoom - 1.0) * e, -spin * e,
                           blur=0.35 + 1.15 * e)
        img = imageops.radial_zoom_blur(img, 0.16 * e ** 2.2, cb.cx, cb.cy, samples=5)
        img = img * (0.70 + 0.30 * (1.0 - e) ** 0.6)
        cx, cy = cb.cx, cb.cy
    # specular bridge at the crossover: warm, centred on the circle
    amp = flash * np.exp(-((w - 0.5) / 0.11) ** 2)
    if amp > 0.01:
        H, W = img.shape[:2]
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (np.hypot(W, H) * 0.5)
        glow = np.exp(-(r ** 2) * 2.4)[..., None] * np.array(warm, dtype=np.float32)
        img = imageops.add_light(img, glow * amp)
    return np.clip(img, 0.0, 1.0)


# --------------------------------------------------------------------------- plan


@dataclass
class MorphPlan:
    """Precomputed data for one transition between two frozen plates."""

    kind: str
    flow: dict | None = None
    ca: Circle | None = None
    cb: Circle | None = None
    center: tuple[float, float] = (540.0, 960.0)
    ellipse: tuple[float, float, float, float] | None = None  # cx, cy, ax, ay, angle
    params: dict = field(default_factory=dict)


def build_plan(kind: str, a: np.ndarray, b: np.ndarray, ca: Circle | None = None,
               cb: Circle | None = None, ellipse=None, center=None, **kwargs) -> MorphPlan:
    """Resolve anchors, then precompute whatever the operator needs.

    Anchors can be passed as numbers, but the films pass feature *names*
    (`measure=("rim", "plate")`) so the circle is detected on the exact endpoint
    frames the morph blends, camera zoom included.
    """
    from . import features

    measure = kwargs.pop("measure", None)
    if measure is not None:  # pragma: no cover - kept for ad-hoc detection
        name_a, name_b = measure
        if name_a in features.CIRCLES:
            ca = features.measure(a, name_a)
        else:
            ellipse = features.measure(a, name_a)
        if name_b:
            cb = features.measure(b, name_b) if name_b in features.CIRCLES else None
    plan = MorphPlan(kind=kind, params=kwargs)
    if kind in {"flow", "hybrid", "portal"}:
        plan.flow = optical_flow(a, b)
    if kind in {"radial", "hybrid", "spin"}:
        plan.ca, plan.cb = ca, cb
        plan.center = ((ca.cx + cb.cx) / 2.0, (ca.cy + cb.cy) / 2.0)
    elif ellipse is not None:
        plan.ellipse = ellipse
        plan.center = (ellipse[0], ellipse[1])
    elif center is not None:
        plan.center = center
    return plan


def render_morph(plan: MorphPlan, a: np.ndarray, b: np.ndarray, w: float) -> np.ndarray:
    w = float(min(1.0, max(0.0, w)))
    if w <= 0.0:
        return a
    if w >= 1.0:
        return b
    p = plan.params
    if plan.kind == "flow":
        return flow_morph(a, b, w, plan.flow, liquid=p.get("liquid", 0.0))
    if plan.kind == "radial":
        res = radial_morph(a, b, w, plan.ca, plan.cb, twist_deg=p.get("twist", 34.0),
                           spiral=p.get("spiral", 0.55), inside=p.get("inside", 1.02),
                           feather=p.get("feather", 26.0))
        outside = a * (1.0 - w) + b * w          # must reach B outside the disc
        return np.clip(res["inside"] * res["mask"] + outside * (1 - res["mask"]), 0, 1)
    if plan.kind == "hybrid":
        res = radial_morph(a, b, w, plan.ca, plan.cb, twist_deg=p.get("twist", 34.0),
                           spiral=p.get("spiral", 0.55), inside=p.get("inside", 1.02),
                           feather=p.get("feather", 30.0))
        outside = flow_morph(a, b, w, plan.flow, liquid=0.0)
        m = res["mask"]
        return np.clip(res["inside"] * m + outside * (1 - m), 0, 1)
    if plan.kind == "portal":
        ex = plan.ellipse
        return portal_morph(a, b, w, ex[0], ex[1], ex[2], ex[3], ex[4],
                            grow=p.get("grow", (0.62, 3.1)), rim=p.get("rim", 1.0))
    if plan.kind == "bloom":
        return bloom_morph(a, b, w, plan.center[0], plan.center[1],
                           warm=p.get("warm", (1.0, 0.72, 0.38)),
                           streak=p.get("streak", 1.0))
    if plan.kind == "spin":
        ca = plan.ca or p.get("ca")
        cb = plan.cb or p.get("cb")
        return spin_through(a, b, w, ca, cb, spin=p.get("spin", 42.0),
                            zoom=p.get("zoom", 1.55), flash=p.get("flash", 0.55),
                            warm=p.get("warm", (1.0, 0.78, 0.52)))
    if plan.kind == "zoom":
        ca = plan.ca or p.get("ca")
        cb = plan.cb or p.get("cb")
        # fall into A's circle, come out of B's circle: the two anchors do not
        # have to share a centre for the move to read as one push
        if ca is not None and cb is not None:
            if w < 0.52:
                k = w / 0.52
                za = 1.0 + (p.get("depth", 2.3) - 1.0) * (k ** 1.6)
                img = _zoom_at(a, ca.cx, ca.cy, za)
                img = imageops.radial_zoom_blur(img, 0.30 * (k ** 2.2), ca.cx, ca.cy, samples=8)
                return np.clip(img * (1.0 - 0.55 * (k ** 3)), 0, 1)
            k = (w - 0.52) / 0.48
            zb = p.get("depth", 2.3) * (1 - k) + k
            img = _zoom_at(b, cb.cx, cb.cy, zb)
            img = imageops.radial_zoom_blur(img, 0.26 * ((1 - k) ** 2.0), cb.cx, cb.cy, samples=8)
            return np.clip(img * (0.45 + 0.55 * (k ** 0.7)), 0, 1)
        return zoom_through(a, b, w, plan.center[0], plan.center[1], depth=p.get("depth", 2.3))
    raise ValueError(f"unknown morph kind {plan.kind}")
