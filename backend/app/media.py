"""Media probing and ffmpeg process helpers.

`av` (PyAV) is used for probing because a static ffmpeg build does not always
ship an `ffprobe` binary; PyAV links libavformat directly and is portable.
All transcoding goes through ffmpeg CLI so filter graphs stay legible.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import get_settings


class MediaError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    path: str
    duration_s: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    has_audio: bool
    audio_rate: int | None
    audio_channels: int | None
    bitrate_kbps: int
    nb_frames: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def probe(path: str | Path) -> MediaInfo:
    import av  # local import: keeps CLI-only paths fast

    p = Path(path)
    if not p.exists():
        raise MediaError(f"file not found: {p}")
    with av.open(str(p)) as container:
        vstream = next((s for s in container.streams if s.type == "video"), None)
        astream = next((s for s in container.streams if s.type == "audio"), None)
        duration = float(container.duration / 1_000_000) if container.duration else 0.0
        width = height = 0
        fps = 0.0
        vcodec = ""
        nb_frames = 0
        if vstream is not None:
            width = int(vstream.codec_context.width or 0)
            height = int(vstream.codec_context.height or 0)
            fps = float(vstream.average_rate) if vstream.average_rate else 0.0
            vcodec = vstream.codec_context.name or ""
            nb_frames = int(vstream.frames or 0)
            if not duration and vstream.duration and vstream.time_base:
                duration = float(vstream.duration * vstream.time_base)
        if not duration:
            # last resort: count in the demuxer
            duration = float(getattr(container, "duration", 0) or 0) / 1_000_000
        return MediaInfo(
            path=str(p),
            duration_s=round(duration, 3),
            width=width,
            height=height,
            fps=round(fps, 3),
            video_codec=vcodec,
            audio_codec=(astream.codec_context.name if astream is not None else None),
            has_audio=astream is not None,
            audio_rate=int(astream.codec_context.sample_rate) if astream is not None else None,
            audio_channels=(astream.codec_context.channels if astream is not None else None),
            bitrate_kbps=int((container.bit_rate or 0) / 1000),
            nb_frames=nb_frames,
        )


def ffmpeg_bin() -> str:
    return get_settings().ffmpeg


def ffmpeg_version() -> str:
    try:
        out = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-version"],
            capture_output=True, text=True, timeout=20,
        )
        return out.stdout.splitlines()[0] if out.stdout else "unavailable"
    except Exception as exc:  # pragma: no cover
        return f"unavailable ({exc})"


def run_ffmpeg(args: list[str], timeout: int = 1800, log_path: Path | None = None) -> str:
    """Run ffmpeg, raise with the tail of stderr on failure."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "warning", "-y", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"ffmpeg timed out after {timeout}s") from exc
    stderr = proc.stderr or ""
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(stderr, encoding="utf-8")
    if proc.returncode != 0:
        tail = "\n".join(stderr.strip().splitlines()[-12:])
        raise MediaError(f"ffmpeg failed ({proc.returncode}):\n{tail}")
    return stderr


def detect_black_and_freeze(path: str | Path, black_min_s: float = 0.25, freeze_min_s: float = 0.6) -> dict[str, Any]:
    """Run ffmpeg's own detectors and parse their stderr output."""
    args = [
        "-i", str(path),
        "-vf", f"blackdetect=d={black_min_s}:pix_th=0.10,freezedetect=n=-60dB:d={freeze_min_s}",
        "-an", "-f", "null", "-",
    ]
    try:
        out = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-nostats", *args],
            capture_output=True, text=True, timeout=300,
        ).stderr
    except Exception as exc:  # pragma: no cover
        return {"error": str(exc), "black_segments": [], "freeze_segments": []}
    black, freeze = [], []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("black_start"):
            black.append(_parse_kv(line))
        elif line.startswith("freeze_start"):
            freeze.append(_parse_kv(line))
    return {"black_segments": black, "freeze_segments": freeze}


def _parse_kv(line: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for token in line.split():
        if ":" in token:
            key, value = token.split(":", 1)
            try:
                out[key] = round(float(value), 3)
            except ValueError:
                continue
    return out


def loudness(path: str | Path) -> dict[str, Any]:
    """EBU R128 integrated loudness via ffmpeg ebur128."""
    args = ["-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"]
    try:
        err = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-nostats", *args],
            capture_output=True, text=True, timeout=300,
        ).stderr
    except Exception as exc:  # pragma: no cover
        return {"error": str(exc)}
    result: dict[str, Any] = {}
    lines = err.splitlines()
    for i, line in enumerate(lines):
        if "Integrated loudness" in line:
            for sub in lines[i + 1 : i + 3]:
                sub = sub.strip()
                if sub.startswith("I:"):
                    result["integrated_lufs"] = float(sub.split()[1])
                elif sub.startswith("Threshold:"):
                    result["threshold_lufs"] = float(sub.split()[1])
        if "True peak" in line:
            for sub in lines[i + 1 : i + 3]:
                sub = sub.strip()
                if sub.startswith("Peak:"):
                    result["true_peak_db"] = float(sub.split()[1])
    return result


def has_binary(name: str) -> bool:
    return shutil.which(name) is not None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
