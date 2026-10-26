"""Safely recover precisely the previously approved 3.68s French WAV from an existing Modal volume.

NO new synthesis and NO GPU. Never substitute a different TTS voice.
The matching SHA-256 was recorded in docs/HUMAN_PERFORMANCE.md.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import wave

import modal

APP = modal.App("pvs-approved-voice-readonly-20261026")
VOLUME = modal.Volume.from_name("pvs-commercial-audio-models", create_if_missing=False)
TARGET_SHA = "7f0b0a1aa0d3184833eb7b93cad36330eeb2c4503bd57f8b942a79c18b236ec6"
MAX_BYTES = 12 * 1024 * 1024


@APP.function(
    image=modal.Image.debian_slim(python_version="3.11"),
    cpu=1, memory=1024, timeout=300,
    volumes={"/models": VOLUME.with_mount_options(read_only=True)},
    max_containers=1,
)
def find_approved():
    root = Path("/models")
    matches_checked = 0
    for folder, subs, filenames in os.walk(root):
        # Skip downloaded weights, caches, and enormous datasets.
        subs[:] = [s for s in subs if s not in {".cache", ".hf_cache", "snapshots", ".git"}]
        for name in filenames:
            if not name.lower().endswith((".wav", ".wave")):
                continue
            source = Path(folder) / name
            try:
                if not 128 < source.stat().st_size <= MAX_BYTES:
                    continue
                data = source.read_bytes()
                matches_checked += 1
                if hashlib.sha256(data).hexdigest() == TARGET_SHA:
                    return {"found": True, "wav_base64": base64.b64encode(data).decode("ascii"),
                            "sha256": TARGET_SHA, "checked_wavs": matches_checked}
            except (OSError, PermissionError):
                pass
    return {"found": False, "checked_wavs": matches_checked}


@APP.local_entrypoint()
def main(out: str = "artifacts/approved_voice_3s68.wav"):
    result = find_approved.remote()
    if not result["found"]:
        print(f"APPROVED_WAV_NOT_FOUND: checked {result['checked_wavs']} existing WAVs. "
              "Stop before GPU rather than substituting another voice.")
        raise SystemExit(3)
    raw = base64.b64decode(result["wav_base64"], validate=True)
    if hashlib.sha256(raw).hexdigest() != TARGET_SHA:
        raise RuntimeError("SHA mismatch in approved French voice")
    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    with wave.open(str(dest), "rb") as w:
        duration = w.getnframes() / w.getframerate()
        if not 3.55 < duration < 3.72 or w.getsampwidth() != 2:
            dest.unlink(missing_ok=True)
            raise RuntimeError("Not the expected 3.68s PCM16 approved sample")
    print(json.dumps({"approved_voice_verified": True, "sha256": TARGET_SHA,
                      "duration_s": round(duration, 4), "bytes": len(raw)}))
