"""Original score and sound design, synthesised from scratch with numpy.

No sample library, no third-party music: everything here is additive/FM
synthesis plus convolution reverb, so the films ship with a clean licence and a
sound that is written for the edit (whooshes land on the morphs, the sub lands
on the cuts). Deliberately sparse: the images carry the film, the music only
gives it a pulse and a room.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, lfilter, sosfilt

SR = 48000


# --------------------------------------------------------------------------- primitives


def t_axis(duration: float, sr: int = SR) -> np.ndarray:
    return np.arange(int(duration * sr), dtype=np.float64) / sr


def env_adsr(n: int, a: float, d: float, s: float, r: float, sr: int = SR) -> np.ndarray:
    a_n, d_n, r_n = int(a * sr), int(d * sr), int(r * sr)
    s_n = max(0, n - a_n - d_n - r_n)
    env = np.concatenate([
        np.linspace(0, 1, max(1, a_n), endpoint=False),
        np.linspace(1, s, max(1, d_n), endpoint=False),
        np.full(s_n, s),
        np.linspace(s, 0, max(1, r_n)),
    ])
    return env[:n] if len(env) >= n else np.pad(env, (0, n - len(env)))


def exp_env(n: int, tau: float, sr: int = SR) -> np.ndarray:
    return np.exp(-t_axis(n / sr, sr)[:n] / max(1e-4, tau))


def saw_additive(freq: float, n: int, sr: int = SR, harmonics: int = 14) -> np.ndarray:
    t = t_axis(n / sr, sr)[:n]
    out = np.zeros(n)
    for k in range(1, harmonics + 1):
        if freq * k > sr * 0.45:
            break
        out += np.sin(2 * np.pi * freq * k * t) / k
    return out * (2.0 / np.pi)


def lowpass(x: np.ndarray, cutoff: float, sr: int = SR) -> np.ndarray:
    sos = butter(2, min(cutoff, sr * 0.45), btype="low", fs=sr, output="sos")
    return sosfilt(sos, x)


def bandpass(x: np.ndarray, lo: float, hi: float, sr: int = SR) -> np.ndarray:
    sos = butter(2, [max(20.0, lo), min(hi, sr * 0.45)], btype="band", fs=sr, output="sos")
    return sosfilt(sos, x)


def pan(x: np.ndarray, p: float) -> np.ndarray:
    """p in [-1, 1]."""
    l = np.sqrt(0.5 * (1.0 - p))
    r = np.sqrt(0.5 * (1.0 + p))
    return np.stack([x * l, x * r], axis=1)


def make_ir(sr: int = SR, seconds: float = 2.1, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    ir = rng.normal(0, 1, (n, 2))
    ir *= np.exp(-t / (seconds * 0.28))[:, None]
    ir[: int(0.012 * sr)] *= np.linspace(0, 1, int(0.012 * sr))[:, None]
    ir = np.stack([lowpass(ir[:, 0], 5200.0, sr), lowpass(ir[:, 1], 5200.0, sr)], axis=1)
    return ir / np.max(np.abs(ir)) * 0.5


def reverb(stereo: np.ndarray, ir: np.ndarray, mix: float = 0.30) -> np.ndarray:
    wet = np.stack([fftconvolve(stereo[:, 0], ir[:, 0])[: len(stereo)],
                    fftconvolve(stereo[:, 1], ir[:, 1])[: len(stereo)]], axis=1)
    return stereo * (1 - mix) + wet * mix * 1.4


# --------------------------------------------------------------------------- instruments


def pad_note(freq: float, n: int, sr: int = SR, detune: float = 0.0045) -> np.ndarray:
    out = np.zeros(n)
    for d in (-detune, 0.0, detune):
        out += saw_additive(freq * (1 + d), n, sr, harmonics=10)
    out /= 3.0
    return lowpass(out, 1400.0, sr) + 0.35 * np.sin(2 * np.pi * freq * t_axis(n / sr, sr)[:n])


def pluck(freq: float, n: int, sr: int = SR, index: float = 2.6, tau: float = 0.42) -> np.ndarray:
    t = t_axis(n / sr, sr)[:n]
    modulator = np.sin(2 * np.pi * freq * 3.01 * t) * index * np.exp(-t / 0.06)
    carrier = np.sin(2 * np.pi * freq * t + modulator)
    carrier += 0.25 * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t / 0.09)
    return carrier * np.exp(-t / tau)


def sub_note(freq: float, n: int, sr: int = SR) -> np.ndarray:
    t = t_axis(n / sr, sr)[:n]
    x = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2 * t)
    return np.tanh(x * 1.25) * 0.8


def add(bus: np.ndarray, x: np.ndarray, at: float, gain: float = 1.0, sr: int = SR,
        stereo: np.ndarray | None = None) -> None:
    i = int(max(0.0, at) * sr)
    if i >= len(bus):
        return
    sig = stereo if stereo is not None else np.stack([x, x], axis=1)
    n = min(len(sig), len(bus) - i)
    bus[i:i + n] += sig[:n] * gain


# --------------------------------------------------------------------------- sfx


def whoosh(duration: float = 0.85, sr: int = SR, low: float = 300.0, high: float = 7000.0,
           seed: int = 5, reverse: bool = False) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    t = np.arange(n) / n
    noise = rng.normal(0, 1, n)
    sweep = low + (high - low) * (t if not reverse else 1 - t) ** 2
    # three fixed bands cross-faded, cheaper and smoother than a swept filter
    bands = [bandpass(noise, 250, 900, sr), bandpass(noise, 900, 2600, sr),
             bandpass(noise, 2600, 8000, sr)]
    w = np.clip(1.0 - np.abs((t - 0.5) * 2 - np.array([0.0, 0.45, 0.9])[:, None]) * 3.0, 0, 1)
    w = np.maximum(w, 0.08)
    x = (bands[0] * w[0] + bands[1] * w[1] * 1.2 + bands[2] * w[2]) / 2.2
    shape = np.sin(np.pi * t) ** 1.6
    if reverse:
        shape = np.linspace(0, 1, n) ** 2.2
    x = x * shape
    return x / (np.max(np.abs(x)) + 1e-9)


def boom(f0: float = 68.0, f1: float = 32.0, duration: float = 1.5, sr: int = SR) -> np.ndarray:
    n = int(duration * sr)
    t = np.arange(n) / sr
    freq = f1 + (f0 - f1) * np.exp(-t / 0.12)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    x = np.sin(phase) * np.exp(-t / 0.55)
    click = bandpass(np.random.default_rng(9).normal(0, 1, n), 1800, 9000, sr) * np.exp(-t / 0.012) * 0.25
    return (x + click) / (np.max(np.abs(x + click)) + 1e-9)


def riser(duration: float = 2.0, sr: int = SR, seed: int = 21) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    t = np.arange(n) / n
    noise = rng.normal(0, 1, n)
    x = bandpass(noise, 600, 5200, sr)
    tone = np.sin(2 * np.pi * (180 + 520 * t ** 2) * np.arange(n) / sr) * 0.25
    shape = t ** 2.4
    x = (x * 0.8 + tone) * shape
    return x / (np.max(np.abs(x)) + 1e-9)


def shimmer(freq: float = 1320.0, duration: float = 2.6, sr: int = SR) -> np.ndarray:
    n = int(duration * sr)
    out = np.zeros(n)
    for k, det in enumerate([1.0, 1.5, 2.0, 3.0]):
        out += pluck(freq * det, n, sr, index=1.4, tau=0.9) / (k + 1.4)
    return out / (np.max(np.abs(out)) + 1e-9)


def engine_rumble(duration: float = 1.8, sr: int = SR, seed: int = 33) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    t = np.arange(n) / sr
    noise = rng.normal(0, 1, n)
    base = bandpass(noise, 60, 320, sr)
    freq = 48 + 26 * np.exp(-t / 0.9)
    tone = np.sin(2 * np.pi * np.cumsum(freq) / sr) * 0.6
    x = (base * 1.1 + tone) * np.exp(-t / 1.1) * np.clip(t / 0.12, 0, 1)
    return x / (np.max(np.abs(x)) + 1e-9)


def sparkle(duration: float = 0.9, sr: int = SR, seed: int = 44) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    t = np.arange(n) / sr
    x = np.zeros(n)
    for _ in range(9):
        f = rng.uniform(2200, 6200)
        at = rng.uniform(0, duration * 0.5)
        idx = int(at * sr)
        m = int(0.12 * sr)
        seg = np.sin(2 * np.pi * f * t[:m]) * np.exp(-t[:m] / 0.03)
        x[idx:idx + m] += seg[: max(0, min(m, n - idx))]
    return x / (np.max(np.abs(x)) + 1e-9)


# --------------------------------------------------------------------------- transport


@dataclass
class Cue:
    name: str
    bpm: float
    chords: list[list[float]]       # frequencies, one list per bar
    chord_seconds: float
    pluck_scale: list[float]
    sub_octave: float = 0.5


def _note(freq: float, n: int, sr: int) -> np.ndarray:
    return pad_note(freq, n, sr)


def render_cue(cue: Cue, duration: float, sfx: list[tuple[float, str]], sr: int = SR) -> np.ndarray:
    n = int(duration * sr)
    bus = np.zeros((n, 2), dtype=np.float64)
    ir = make_ir(sr)

    # pads: one chord per window, long cross-faded attack
    pad_bus = np.zeros((n, 2))
    t0 = 0.0
    idx = 0
    while t0 < duration:
        chord = cue.chords[idx % len(cue.chords)]
        length = min(cue.chord_seconds * 1.12, duration - t0 + 0.4)
        m = int(length * sr)
        if m > 24:
            for j, f in enumerate(chord):
                x = pad_note(f, m, sr)
                x *= env_adsr(m, 0.55, 0.5, 0.72, 0.6, sr)
                voice = np.zeros((n, 2), dtype=np.float64)
                start = int(t0 * sr)
                end = min(n, start + m)
                voice[start:end] = pan(x, (-0.35 + 0.22 * j) * 0.9)[: end - start]
                pad_bus += voice
            root = chord[0] * cue.sub_octave
            s = sub_note(root, m, sr) * env_adsr(m, 0.06, 0.35, 0.55, 0.8, sr)
            add(bus, s, t0, gain=0.16)
        t0 += cue.chord_seconds
        idx += 1
    pad_bus *= 0.085
    bus += reverb(pad_bus, ir, mix=0.42)

    # sparse pluck motif, deterministic and musical
    rng = np.random.default_rng({"food": 5, "auto": 8}.get(cue.name, 6))
    beat = 60.0 / cue.bpm
    step = beat * 0.5
    tt = 0.0
    k = 0
    scale = cue.pluck_scale
    while tt < duration - 0.6:
        if k % 7 in (0, 3, 5):          # sparse, never a machine-gun arpeggio
            f = scale[int(rng.integers(0, len(scale)))] * (2.0 if rng.random() < 0.22 else 1.0)
            m = int(2.2 * sr)
            x = pluck(f, m, sr, tau=0.7) * 0.20
            add(bus, None, tt, gain=1.0, sr=sr,
                stereo=reverb(pan(x, float(rng.uniform(-0.6, 0.6))), ir, mix=0.5))
        tt += step
        k += 1

    # low pulse: half notes, very restrained
    beat = 60.0 / cue.bpm
    for i, at in enumerate(np.arange(beat * 2, duration - 0.4, beat * 2)):
        x = np.sin(2 * np.pi * (cue.chords[0][0] * cue.sub_octave) * np.arange(int(0.35 * sr)) / sr)
        x *= np.exp(-np.arange(int(0.35 * sr)) / (0.09 * sr))
        add(bus, x, at, gain=0.085)

    # air bed
    rng2 = np.random.default_rng(77)
    air = bandpass(rng2.normal(0, 1, n), 3200, 11000, sr) * 0.016
    air *= np.clip(np.linspace(0, 1, n) * 2.2, 0, 1) * np.clip(np.linspace(1, 0, n) * 6.0, 0, 1)
    bus += np.stack([air, np.roll(air, 240)], axis=1)

    # sound design, synced to the edit
    for at, kind in sfx:
        if kind == "whoosh":
            x = whoosh(0.9, sr, 260, 7600, seed=int(at * 100) % 999)
            add(bus, None, at - 0.42, gain=0.30, sr=sr, stereo=pan(x, -0.25))
            add(bus, None, at - 0.38, gain=0.22, sr=sr,
                stereo=pan(whoosh(0.85, sr, 400, 9000, seed=int(at * 100) % 998, reverse=True), 0.35))
        elif kind == "boom":
            add(bus, boom(), at - 0.05, gain=0.55)
        elif kind == "riser":
            add(bus, riser(2.0, sr, seed=int(at * 10) % 500), at - 1.95, gain=0.22)
        elif kind == "shimmer":
            add(bus, None, at, gain=0.22, sr=sr, stereo=reverb(pan(shimmer(1180.0, 2.8, sr), 0.0), ir, 0.6))
        elif kind == "rumble":
            add(bus, None, at, gain=0.30, sr=sr, stereo=pan(engine_rumble(2.0, sr), -0.15))
        elif kind == "sparkle":
            add(bus, None, at, gain=0.18, sr=sr, stereo=pan(sparkle(1.0, sr), 0.4))

    # gentle bus compression, then a transparent safety limiter (no hard clip:
    # crushing the mix to tanh killed the transients and the loudness range)
    level = np.abs(bus).max(axis=1)
    env = lfilter([0.004], [1.0, -0.996], level)
    gain = np.where(env > 0.20, 0.20 / np.maximum(env, 1e-6), 1.0) ** 0.30
    bus = bus * gain[:, None]
    peak = float(np.max(np.abs(bus))) or 1.0
    bus = bus / peak * 1.15
    bus = np.where(np.abs(bus) > 0.92, np.sign(bus) * (0.92 + 0.06 * np.tanh((np.abs(bus) - 0.92) / 0.06)), bus)

    # fades
    fade_in = int(0.25 * sr)
    fade_out = int(1.1 * sr)
    bus[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    bus[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None] ** 1.3
    peak = np.max(np.abs(bus))
    return bus / max(1e-9, peak) * 0.95


def write_wav(path: str | Path, stereo: np.ndarray, sr: int = SR) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(data.tobytes())


# --------------------------------------------------------------------------- cues

D3, E3, Fs3, G3, A3, B3, Cs4, D4, E4, Fs4, A4, B4, Cs5, E5, Fs5, A5 = (
    146.83, 164.81, 185.00, 196.00, 220.00, 246.94, 277.18, 293.66, 329.63, 369.99,
    440.00, 493.88, 554.37, 659.25, 739.99, 880.00)


def food_cue() -> Cue:
    return Cue(
        name="food", bpm=66.0,
        chords=[[D3, A3, Cs4, E4], [B3 * 0.5, D3, Fs3, A3], [G3, B3, D4, Fs4], [A3 * 0.5, Cs4, E4, G3]],
        chord_seconds=3.6,
        pluck_scale=[D4, Fs4, A4, B4, Cs5, E5, Fs5, A5],
    )


def auto_cue() -> Cue:
    return Cue(
        name="auto", bpm=92.0,
        chords=[[Fs3 * 0.5, Cs4, Fs4, A4], [D3, A3, Cs4, Fs4], [A3 * 0.5, Cs4, E4, A4], [E3, B3, D4, G3]],
        chord_seconds=3.2,
        pluck_scale=[Fs5, A5, Cs5, E5, Fs4, A4, Cs4],
    )
