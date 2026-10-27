"""Tests for the portfolio morph engine (CPU only, no GPU, no Modal).

What is worth testing here is what actually broke during production:
endpoint exactness (a morph must land exactly on the next shot), projection
against the real camera transform, the film timeline (a transition window must
win over the shots it joins) and the score's dynamic range.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from scripts.portfolio.morphfilm import anchors, camera, films, imageops, morph, score
from scripts.portfolio.morphfilm.anchors import Endpoint

WORK = Path(__file__).resolve().parents[1] / "data" / "portfolio-2026-10-23"


def _fake_plate(seed: int = 0, w: int = 216, h: int = 384) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    img[..., 0] = 0.35 + 0.3 * np.sin(xx / 12.0) ** 2
    img[..., 1] = 0.30 + 0.3 * np.cos(yy / 9.0) ** 2
    img[..., 2] = 0.25 + 0.2 * np.sin((xx + yy) / 17.0) ** 2
    img += rng.normal(0, 0.01, img.shape).astype(np.float32)
    return np.clip(img, 0, 1)


# --------------------------------------------------------------------------- anchors


def test_projection_matches_the_camera_inverse():
    """The anchor projection must be the exact inverse of `Plate.render`."""
    path = WORK / "food" / "f2-plate.png"
    if not path.is_file():
        pytest.skip("plates absentes")
    ep = Endpoint(overscan=1.24, zoom=1.13, pan=(0.004, -0.002), roll=0.7)
    plate = camera.Plate(path, 1080, 1920, overscan=ep.overscan)
    # a synthetic marker at the native position, then located in the render
    native = anchors.NATIVE_CIRCLES["plate"]
    canvas_x = native[0] * anchors.K * ep.overscan
    canvas_y = native[1] * anchors.K * ep.overscan
    cx, cy = int(round(canvas_x)), int(round(canvas_y))
    marked = plate.img.copy()
    marked[cy - 6:cy + 7, cx - 6:cx + 7] = np.array([1.0, 0.0, 1.0], np.float32)
    plate.img = marked
    frame = plate.render(camera.Cam(zoom=ep.zoom, pan_x=ep.pan[0], pan_y=ep.pan[1],
                                    roll_deg=ep.roll))
    magenta = (frame[..., 0] > 0.75) & (frame[..., 1] < 0.35) & (frame[..., 2] > 0.75)
    assert magenta.sum() > 20, "le marqueur a disparu du rendu"
    ys, xs = np.nonzero(magenta)
    expected = anchors.circle("plate", ep)
    assert abs(xs.mean() - expected.cx) < 4.0
    assert abs(ys.mean() - expected.cy) < 4.0


def test_radius_scales_with_overscan_and_zoom():
    base = anchors.circle("plate", Endpoint(1.0, 1.0))
    zoomed = anchors.circle("plate", Endpoint(1.0, 2.0))
    assert zoomed.r == pytest.approx(base.r * 2.0, rel=1e-6)
    wider = anchors.circle("plate", Endpoint(1.5, 1.0))
    assert wider.r == pytest.approx(base.r * 1.5, rel=1e-6)


def test_derived_wheel_stays_inside_its_plate():
    ep = Endpoint(1.12, 1.02, (0.004, 0.0), 5.0)
    c = anchors.circle("wheel", ep)
    assert 0 < c.cx < 1080 and 0 < c.cy < 1920
    assert c.r > 0


# --------------------------------------------------------------------------- morphs


@pytest.mark.parametrize("kind", ["spin", "zoom", "flow", "portal", "bloom", "radial"])
def test_morph_is_exact_at_both_endpoints(kind):
    a, b = _fake_plate(1), _fake_plate(2)
    ca = morph.Circle(a.shape[1] / 2, a.shape[0] / 2, a.shape[1] * 0.35)
    cb = morph.Circle(b.shape[1] / 2, b.shape[0] / 2, b.shape[1] * 0.32)
    kwargs = dict(ca=ca, cb=cb)
    if kind == "portal":
        kwargs = dict(ellipse=(a.shape[1] / 2, a.shape[0] / 2, 60.0, 110.0, 4.0))
    plan = morph.build_plan(kind, a, b, **kwargs)
    assert np.array_equal(morph.render_morph(plan, a, b, 0.0), a)
    assert np.array_equal(morph.render_morph(plan, a, b, 1.0), b)


@pytest.mark.parametrize("kind", ["spin", "zoom", "flow", "portal", "bloom", "radial"])
def test_morph_output_is_a_valid_image(kind):
    a, b = _fake_plate(3), _fake_plate(4)
    ca = morph.Circle(a.shape[1] / 2, a.shape[0] / 2, a.shape[1] * 0.35)
    cb = morph.Circle(b.shape[1] / 2, b.shape[0] / 2, b.shape[1] * 0.32)
    kwargs = dict(ca=ca, cb=cb)
    if kind == "portal":
        kwargs = dict(ellipse=(a.shape[1] / 2, a.shape[0] / 2, 60.0, 110.0, 4.0))
    plan = morph.build_plan(kind, a, b, **kwargs)
    for w in np.linspace(0.05, 0.95, 7):
        out = morph.render_morph(plan, a, b, float(w))
        assert out.shape == a.shape
        assert np.isfinite(out).all(), f"{kind} produit des NaN à w={w}"
        assert out.min() >= 0.0 and out.max() <= 1.0


def test_spin_through_never_blends_two_photographs():
    """The signature transition must show one source at a time, not a dissolve."""
    a, b = _fake_plate(5), _fake_plate(6)
    ca = morph.Circle(108, 192, 70)
    cb = morph.Circle(108, 192, 66)
    plan = morph.build_plan("spin", a, b, ca=ca, cb=cb, spin=50.0, zoom=1.6, flash=0.0)
    out = morph.render_morph(plan, a, b, 0.5)
    # at the crossover the frame is a transformed B, not an average of A and B
    blended = 0.5 * a + 0.5 * b
    assert np.abs(out - blended).mean() > 0.05


def test_median_edge_score_prefers_the_real_circle():
    img = _fake_plate(7, 240, 240)
    yy, xx = np.mgrid[0:240, 0:240]
    r = np.sqrt((xx - 120) ** 2 + (yy - 120) ** 2)
    ring = ((r > 60) & (r < 64))[..., None]
    img = np.where(ring, np.array([1.0, 1.0, 1.0], np.float32), img)
    from scripts.portfolio.morphfilm import features
    good = features._score_circle(features._edge_map(img),
                                  (120 + 62 * np.cos(np.linspace(0, 6.28, 200)))[None, :],
                                  (120 + 62 * np.sin(np.linspace(0, 6.28, 200)))[None, :])
    bad = features._score_circle(features._edge_map(img),
                                 (120 + 20 * np.cos(np.linspace(0, 6.28, 200)))[None, :],
                                 (120 + 20 * np.sin(np.linspace(0, 6.28, 200)))[None, :])
    assert good.mean() > bad.mean() * 2.0


# --------------------------------------------------------------------------- timeline


def _tiny_film():
    plate = camera.Plate(WORK / "food" / "f1-rim.png", 108, 192, overscan=1.1) \
        if (WORK / "food" / "f1-rim.png").is_file() else None
    if plate is None:
        pytest.skip("plates absentes")
    shots = [films.Shot("a", plate, 2.0, cam=lambda u: camera.Cam(zoom=1.0 + 0.1 * u)),
             films.Shot("b", plate, 2.0, cam=lambda u: camera.Cam(zoom=1.1 - 0.1 * u))]
    tr = [films.Transition("t", "spin", 0.6, params={
        "ca": morph.Circle(54, 96, 40), "cb": morph.Circle(54, 96, 42)})]
    return films.Film(slug="test", title="test", shots=shots, transitions=tr, fps=6,
                      grade=imageops.Grade(), endcard={"kicker": "t", "line": "l", "note": "n",
                                                      "duration": 0.5})


def test_timeline_overlaps_and_duration():
    film = _tiny_film()
    sched = film.schedule()
    assert sched[1][0] == pytest.approx(1.4)
    assert film.duration == pytest.approx(3.4)


def test_transition_window_wins_over_the_shots_it_joins():
    film = _tiny_film()
    renderer = __import__("scripts.portfolio.morphfilm.film", fromlist=["Renderer"]).Renderer(
        film, WORK)
    _, info = renderer.frame(1.7)          # inside the 1.4 -> 2.0 transition
    assert "transition" in info
    _, info = renderer.frame(0.4)          # plainly inside shot a
    assert info.get("shot") == "a"


# --------------------------------------------------------------------------- score


def test_score_is_clean_and_loud_enough():
    cue = score.food_cue()
    events = [(1.0, "whoosh"), (2.0, "boom"), (2.5, "shimmer")]
    audio = score.render_cue(cue, 4.0, events)
    assert np.isfinite(audio).all()
    assert np.abs(audio).max() <= 1.0
    assert np.abs(audio).max() > 0.5, "mixage trop faible"
    # stereo and not a duplicated mono channel
    assert audio.shape[1] == 2
    assert np.abs(audio[:, 0] - audio[:, 1]).max() > 1e-4


def test_whoosh_and_boom_are_normalised():
    for fn in (score.whoosh, score.boom, score.riser):
        x = fn(1.0)
        assert np.isfinite(x).all()
        assert np.abs(x).max() == pytest.approx(1.0, abs=1e-6)


# --------------------------------------------------------------------------- image ops


def test_grade_keeps_range_and_adds_no_nan():
    img = _fake_plate(8)
    out = imageops.apply_grade(img, imageops.Grade(), imageops.GrainBank(), grain_index=3)
    assert np.isfinite(out).all()
    assert 0.0 <= out.min() and out.max() <= 1.0
    assert out.std() > 0.01


def test_cover_fit_keeps_the_aspect_ratio():
    img = imageops.load_cover(WORK / "food" / "f1-rim.png", 108, 192) \
        if (WORK / "food" / "f1-rim.png").is_file() else None
    if img is None:
        pytest.skip("plates absentes")
    assert img.shape == (192, 108, 3)
