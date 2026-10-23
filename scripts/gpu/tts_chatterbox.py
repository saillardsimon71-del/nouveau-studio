#!/usr/bin/env python3
"""French voice synthesis with Chatterbox Multilingual (V3 by default).

Runs inside the TTS environment, called by the studio's `chatterbox` adapter.
The studio never imports torch: model stacks stay on the GPU host, the API
process stays light.

    pip install chatterbox-tts
    python tts_chatterbox.py --check
    python tts_chatterbox.py --text "Bonjour" --out /tmp/a.wav --language fr \
        --speaker-wav ref.wav --exaggeration 0.55

Reference (upstream README): multilingual model accepts `language_id="fr"`, and
`exaggeration` / `cfg_weight` control delivery. French is in the supported list.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def check() -> int:
    try:
        import torch  # noqa: F401
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # noqa: F401
    except Exception as exc:  # pragma: no cover - host dependent
        print(f"Chatterbox indisponible: {exc}", file=sys.stderr)
        return 2
    print("Chatterbox OK")
    try:
        import torch

        print(f"cuda={torch.cuda.is_available()} devices={torch.cuda.device_count()}")
    except Exception:
        pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--text", default="")
    parser.add_argument("--out", default="out.wav")
    parser.add_argument("--language", default="fr")
    parser.add_argument("--speaker-wav", default=None)
    parser.add_argument("--exaggeration", type=float, default=0.55)
    parser.add_argument("--cfg-weight", type=float, default=0.5)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--model", default="v3")
    args = parser.parse_args()

    if args.check:
        return check()
    if not args.text.strip():
        print("texte vide", file=sys.stderr)
        return 2

    import torch
    import torchaudio as ta
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    started = time.time()
    model = ChatterboxMultilingualTTS.from_pretrained(device=device, t3_model=args.model)
    kwargs = {
        "language_id": args.language,
        "exaggeration": args.exaggeration,
        "cfg_weight": args.cfg_weight,
        "temperature": args.temperature,
    }
    if args.speaker_wav:
        if not Path(args.speaker_wav).exists():
            print(f"échantillon introuvable: {args.speaker_wav}", file=sys.stderr)
            return 2
        kwargs["audio_prompt_path"] = args.speaker_wav

    wav = model.generate(args.text, **kwargs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ta.save(str(out), wav, model.sr)
    print(f"wrote {out} in {time.time() - started:.1f}s (device={device}, sr={model.sr})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
