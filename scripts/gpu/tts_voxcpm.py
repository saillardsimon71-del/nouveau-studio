#!/usr/bin/env python3
"""French voice synthesis with VoxCPM2 (2B, 30 languages, 48 kHz out).

Alternative to Chatterbox when audio quality matters more than latency:
~8 GB VRAM, RTF ≈ 0.30 on an RTX 4090 with the reference implementation.

    pip install voxcpm
    python tts_voxcpm.py --check
    python tts_voxcpm.py --text "Bonjour" --out /tmp/a.wav --language fr --speaker-wav ref.wav
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def check() -> int:
    try:
        import torch  # noqa: F401
        from voxcpm import VoxCPM  # noqa: F401
    except Exception as exc:  # pragma: no cover
        print(f"VoxCPM indisponible: {exc}", file=sys.stderr)
        return 2
    print("VoxCPM OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--text", default="")
    parser.add_argument("--out", default="out.wav")
    parser.add_argument("--language", default="fr")
    parser.add_argument("--speaker-wav", default=None)
    parser.add_argument("--cfg-weight", type=float, default=2.0)
    parser.add_argument("--model", default="openbmb/VoxCPM2")
    args = parser.parse_args()
    if args.check:
        return check()
    if not args.text.strip():
        print("texte vide", file=sys.stderr)
        return 2

    import soundfile as sf
    import torch
    from voxcpm import VoxCPM

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = VoxCPM.from_pretrained(args.model, load_denoiser=False, device=device)
    started = time.time()
    wav = model.generate(
        text=args.text,
        reference_wav_path=args.speaker_wav,
        cfg_value=args.cfg_weight,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), wav, model.tts_model.sample_rate)
    print(f"wrote {out} in {time.time() - started:.1f}s (device={device})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
