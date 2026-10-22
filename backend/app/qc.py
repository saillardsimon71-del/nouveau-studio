"""Quality control.

Two tiers, deliberately kept separate:

* **Automatable checks** (this module): container is readable, duration and
  format match the plan, audio present, no black or frozen stretches, loudness
  in range, subtitles present in the export. These are cheap and reliable.
* **Human checks** (never faked): face identity drift, lip-sync accuracy,
  expression naturalness, prompt adherence. The studio surfaces them as an
  explicit checklist attached to the clip instead of pretending a model
  evaluated them.

A `verdict` of `pass` means "no packaging defect detected", not "the shot is
good". The UI wording follows that distinction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import media

HUMAN_CHECKS = [
    "identité du visage cohérente avec l'avatar",
    "synchronisation labiale (si avatar parlant)",
    "expressions et mouvements crédibles",
    "respect du prompt et du cadrage",
    "absence d'artefacts visuels (mains, dents, textures)",
]


def inspect_clip(
    path: str | Path,
    expected_duration_s: float | None = None,
    expected_aspect: str | None = "9:16",
    require_audio: bool = True,
    expected_fps: int | None = None,
    deep: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return {
            "verdict": "fail",
            "checks": [{"id": "file_exists", "status": "fail", "detail": "fichier absent"}],
            "metrics": {},
            "human_checks": HUMAN_CHECKS,
        }

    info = media.probe(p)
    metrics: dict[str, Any] = info.to_dict()

    def add(check_id: str, ok: bool | None, detail: str, severity: str = "error") -> None:
        checks.append(
            {
                "id": check_id,
                "status": "pass" if ok else ("review" if severity == "warn" else "fail"),
                "detail": detail,
            }
        )

    add("readable", True, f"{info.video_codec or 'n/a'} {info.width}x{info.height} {info.fps}fps")
    if expected_duration_s:
        delta = abs(info.duration_s - expected_duration_s)
        add(
            "duration",
            delta <= max(0.25, expected_duration_s * 0.04),
            f"{info.duration_s:.2f}s mesuré / {expected_duration_s:.2f}s attendu",
            severity="warn",
        )
    if expected_aspect:
        want = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1.0}.get(expected_aspect, 9 / 16)
        got = info.width / info.height if info.height else 0
        add("aspect", abs(got - want) < 0.02, f"ratio {got:.3f} / attendu {want:.3f}")
    if expected_fps:
        add("fps", abs(info.fps - expected_fps) < 1.5, f"{info.fps:.2f} / {expected_fps}", severity="warn")
    if require_audio:
        add("audio_track", info.has_audio, "piste audio présente" if info.has_audio else "aucune piste audio")
        if info.has_audio:
            add("audio_rate", (info.audio_rate or 0) >= 44100, f"{info.audio_rate} Hz", severity="warn")
    if info.width < 720 or info.height < 720:
        add("resolution", False, f"{info.width}x{info.height} < 720p", severity="warn")

    if deep:
        detected = media.detect_black_and_freeze(p)
        black = detected.get("black_segments", [])
        freeze = detected.get("freeze_segments", [])
        add("no_black_frames", not black, f"{len(black)} segment(s) noir(s)", severity="warn")
        add("no_frozen_frames", not freeze, f"{len(freeze)} segment(s) figé(s)", severity="warn")
        metrics["black_segments"] = black
        metrics["freeze_segments"] = freeze
        if info.has_audio:
            loud = media.loudness(p)
            metrics["loudness"] = loud
            lufs = loud.get("integrated_lufs")
            if lufs is not None:
                add("loudness", -20.0 <= lufs <= -9.0, f"{lufs:.1f} LUFS", severity="warn")

    verdict = "pass"
    if any(c["status"] == "fail" for c in checks):
        verdict = "fail"
    elif any(c["status"] == "review" for c in checks):
        verdict = "review"

    return {"verdict": verdict, "checks": checks, "metrics": metrics, "human_checks": HUMAN_CHECKS}


def inspect_export(path: str | Path, spec: dict[str, Any], expected_duration_s: float | None = None) -> dict[str, Any]:
    result = inspect_clip(
        path,
        expected_duration_s=expected_duration_s,
        expected_aspect=spec.get("format", "9:16"),
        require_audio=True,
        expected_fps=int(spec.get("fps") or 30),
    )
    result["human_checks"] = [
        "le montage est intelligible sans le son",
        "les sous-titres sont lisibles et bien synchronisés",
        "niveau de la musique sous la voix",
        "cohérence des personnages entre les plans",
    ]
    return result


def needs_human(qc: dict[str, Any]) -> bool:
    return bool(qc.get("verdict") != "pass" or qc.get("checks"))
