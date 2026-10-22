#!/usr/bin/env python3
"""Validate the benchmark inputs before spending a single GPU second.

Two files are required:

  benchmark_assets/character_reference.png   vertical portrait, >= 512 px wide
  benchmark_assets/voice_reference_fr.wav    10 s of spoken French, >= 16 kHz

No network, no ffmpeg dependency: the PNG header and the WAV chunks are parsed
with the standard library, so this runs in CI and on the phone-hosted workflow
alike. Exit code 1 means "do not launch a benchmark".

    python scripts/check_benchmark_assets.py [--warn-only]
"""

from __future__ import annotations

import struct
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS = REPO_ROOT / "benchmark_assets"
PNG = ASSETS / "character_reference.png"
WAV = ASSETS / "voice_reference_fr.wav"

MIN_PNG_SIDE = 512
MIN_WAV_SECONDS = 3.0
MAX_WAV_SECONDS = 60.0
MIN_WAV_RATE = 16000


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(33)
    if len(header) < 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("not a PNG (bad signature or missing IHDR)")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def check_png() -> tuple[bool, str]:
    if not PNG.is_file():
        return False, f"absent: {PNG.relative_to(REPO_ROOT)} — voir benchmark_assets/README.md"
    try:
        width, height = png_size(PNG)
    except (OSError, ValueError) as exc:
        return False, f"illisible: {exc}"
    problems = []
    if min(width, height) < MIN_PNG_SIDE:
        problems.append(f"trop petit ({width}x{height}, min {MIN_PNG_SIDE} px sur le petit côté)")
    if height <= width:
        problems.append(f"pas vertical ({width}x{height}); le format cible est 9:16")
    size_mb = PNG.stat().st_size / (1024 * 1024)
    if size_mb > 24:
        problems.append(f"{size_mb:.1f} MiB > 24 MiB acceptés par l'app Modal")
    if problems:
        return False, f"{width}x{height}, {size_mb:.2f} MiB — " + " ; ".join(problems)
    return True, f"{width}x{height}, {size_mb:.2f} MiB, PNG valide"


def check_wav() -> tuple[bool, str]:
    if not WAV.is_file():
        return False, (
            f"absent: {WAV.relative_to(REPO_ROOT)} — enregistrer 10 s de français "
            "et l'ajouter (voir benchmark_assets/README.md)"
        )
    try:
        with wave.open(str(WAV), "rb") as audio:
            channels = audio.getnchannels()
            width = audio.getsampwidth()
            rate = audio.getframerate()
            frames = audio.getnframes()
            raw = audio.readframes(frames)
    except (OSError, wave.Error) as exc:
        return False, f"WAV illisible: {exc}"
    seconds = frames / rate if rate else 0.0
    problems = []
    if rate < MIN_WAV_RATE:
        problems.append(f"{rate} Hz < {MIN_WAV_RATE} Hz")
    if width != 2:
        problems.append(f"{width * 8} bits/échantillon; convertir en PCM 16 bits")
    if not MIN_WAV_SECONDS <= seconds <= MAX_WAV_SECONDS:
        problems.append(f"{seconds:.1f} s hors de {MIN_WAV_SECONDS:.0f}-{MAX_WAV_SECONDS:.0f} s")
    # crude loudness check: a silent file must not pass as a voice reference
    peak = 0
    if width == 2 and raw:
        peak = max(abs(v) for v in struct.unpack("<%dh" % (len(raw) // 2), raw[: len(raw) // 2 * 2]))
    if peak < 500:
        problems.append(f"quasi silencieux (crête {peak}/32767)")
    label = f"{seconds:.1f} s, {rate} Hz, {channels} canal(aux), {width * 8} bits, crête {peak}"
    if problems:
        return False, f"{label} — " + " ; ".join(problems)
    return True, label


def main() -> int:
    warn_only = "--warn-only" in sys.argv[1:]
    ok = True
    for name, (passed, detail) in (("image de référence", check_png()), ("voix française", check_wav())):
        status = "OK  " if passed else "FAIL"
        print(f"[{status}] {name}: {detail}")
        ok = ok and passed
    if not ok:
        if warn_only:
            print("\n(mode informatif : le run continue, mais les tests B/C seraient invalides)")
            return 0
        print("\nBenchmark bloqué : fournir les deux fichiers, puis relancer.")
        return 1
    print("\nInputs valides : un run GPU peut être lancé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
