#!/usr/bin/env python3
"""A/B audio-only postproduction comparison on the REAL ÉCLAT 01 speaking ad clip.

No GPU, no inference, no changes to any approved source. Uses the exact same
source scene and licensed score in both variants; only music_ducking differs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import media, qc  # noqa: E402
from app.engines.assembly import AssemblyEngine  # noqa: E402
from app.engines.base import EngineRequest  # noqa: E402

SOURCE_ROOT = ROOT / "inputs" / "eclat"
OUT = ROOT / "artifacts" / "audio-ab"
MUSIC_URL = "https://www.scottbuckley.com.au/library/wp-content/uploads/2019/02/sb_ascension.mp3"
MUSIC_PAGE = "https://www.scottbuckley.com.au/library/ascension/"
DIALOGUE = "Et si le luxe commençait par prendre soin de soi ?"
# New/old mixes use the same deliberately audible music level. This is an
# A/B for comparative audition, not a proposed final mastering recommendation.
MUSIC_GAIN_DB = -14.0


class Context:
    job_id = "eclat01-audio-ab-cpu"

    def log(self, message: str, **kwargs) -> None:
        print(message, flush=True)

    def check_cancelled(self) -> None:
        return


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_speaking_clip() -> Path:
    clips = sorted(SOURCE_ROOT.rglob("beauty-spokesperson.mp4"))
    if len(clips) != 1:
        raise RuntimeError(f"Expected exactly one original talking scene, found {len(clips)} under {SOURCE_ROOT}")
    clip = clips[0]
    info = media.probe(clip)
    if not info.has_audio or info.duration_s < 4.0:
        raise RuntimeError("Real source clip is too short or missing native H3 audio.")
    print(f"REAL SCENE: {clip} ({info.duration_s:.3f}s, native audio)", flush=True)
    return clip


def licensed_music() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT / "score.mp3"
    req = urllib.request.Request(MUSIC_URL, headers={"User-Agent": "Mozilla/5.0 SiteQuiVend-AudioAB/1.0"})
    with urllib.request.urlopen(req, timeout=90) as response:
        blob = response.read(25_000_001)
    if not 100_000 < len(blob) < 25_000_000:
        raise RuntimeError("Licensed score download did not meet expected size bounds")
    destination.write_bytes(blob)
    if not media.probe(destination).has_audio:
        raise RuntimeError("The licensed score has no audio")
    return destination


def render_variant(clip: Path, score: Path, label: str, ducking: bool, duration: float) -> dict:
    work = OUT / f"work_{label}"
    request = EngineRequest(
        kind="assembly",
        output_dir=work,
        project={"name": "ÉCLAT 01 — comparatif mixage", "format": "9:16"},
        params={
            "format": "9:16",
            "fps": 24,
            "subtitles": False,
            "transitions": False,
            "title_card": False,
            "music_path": str(score),
            "music_gain_db": MUSIC_GAIN_DB,
            "music_ducking": ducking,
            "loudness_target": -14,
        },
        inputs={"clips": [
            {"path": str(clip), "duration_s": duration, "dialogue": DIALOGUE,
             "kind": "product", "transition": "cut"}
        ]},
    )
    output = AssemblyEngine().run(request, Context())
    applied = bool(output.diagnostics["music_ducking"])
    if applied != ducking:
        raise AssertionError(f"Music ducking mismatch: requested={ducking}, actual={applied}")
    video_artifact = next(a for a in output.artifacts if a["kind"] == "export")
    generated = Path(video_artifact["path"])
    final = OUT / f"ECLAT01-{label}-{'DUCKING' if ducking else 'SANS-DUCKING'}.mp4"
    shutil.copy2(generated, final)
    audio = final.with_suffix(".m4a")
    media.run_ffmpeg(["-i", str(final), "-vn", "-c:a", "copy", str(audio)])
    spec = {"format": "9:16", "fps": 24}
    check = qc.inspect_export(final, spec, expected_duration_s=duration)
    loudness = media.loudness(final)
    info = media.probe(final)
    return {
        "label": label, "ducking_requested": ducking, "ducking_applied": applied,
        "video": final.name, "audio": audio.name, "sha256": sha256(final),
        "duration_s": info.duration_s, "width": info.width, "height": info.height,
        "fps": info.fps, "audio_present": info.has_audio,
        "loudness": loudness, "qc": check,
    }


def main() -> None:
    clip = find_speaking_clip()
    score = licensed_music()
    duration = round(min(4.5, media.probe(clip).duration_s - 0.05), 3)
    if duration < 3.5:
        raise RuntimeError("Original spoken clip too short for a fair comparison")
    before = render_variant(clip, score, "A", False, duration)
    after = render_variant(clip, score, "B", True, duration)
    if not before["audio_present"] or not after["audio_present"]:
        raise RuntimeError("Export missing audio")
    if abs(before["duration_s"] - after["duration_s"]) > 0.15:
        raise RuntimeError("A/B exports differ in duration")
    if before["width"] != after["width"] or before["height"] != after["height"]:
        raise RuntimeError("A/B exports differ in image geometry")
    report = {
        "date": "2026-10-26", "provenance": {
            "video": "Original native-audio H3 ÉCLAT 01 beauty-spokesperson scene",
            "source_run_id": 40195429662,
            "source_clip_sha256": sha256(clip),
            "original_script": "scripts/production/eclat_01_h3.py",
            "score": "'Ascension' by Scott Buckley, CC BY 4.0",
            "score_page": MUSIC_PAGE, "score_sha256": sha256(score),
        },
        "controls": {
            "unchanged_between_variants": ["source video", "source audio", "score", "score gain",
                                            "resolution", "fps", "duration", "LUFS target"],
            "difference": "music_ducking False / True",
            "score_gain_db": MUSIC_GAIN_DB,
            "dialogue_text_expected_from_prompt": DIALOGUE,
            "limitation": "Speech quality and perceptual clarity require HUMAN listening; metrics cannot prove improvement.",
        },
        "A": before, "B": after,
        "technical_comparison": {
            "same_duration_tolerance_s": 0.15,
            "same_source_media": True,
            "gpu_calls": 0, "paid_api_calls": 0,
        },
    }
    (OUT / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "README.txt").write_text(
        "ÉCLAT / 01 — comparatif audio A/B, vraie scène vidéo avec voix native française.\n"
        "A = musique à niveau fixe ; B = musique atténuée par la voix (sidechain).\n"
        "Même voix, même scène, même musique CC BY 4.0, même cible -14 LUFS.\n"
        "Comparer surtout l'intelligibilité de la phrase parlée, l'ambiance et les artefacts de pompage.\n"
        "ATTENTION: le passage QC signifie absence de défaut technique, pas meilleure qualité audible.\n"
        "L'audio natif H3 peut avoir des défauts de diction non résolus par le mixage.\n"
        f"Musique : Ascension — Scott Buckley, CC BY 4.0 — {MUSIC_PAGE}\n"
        "Source : SiteQuiVend ÉCLAT 01, concept publicitaire fictif.\n",
        encoding="utf-8",
    )
    print("A/B SUCCESS:", json.dumps({
        "A": {"video": before["video"], "qc": before["qc"]["verdict"], "loudness": before["loudness"]},
        "B": {"video": after["video"], "qc": after["qc"]["verdict"], "loudness": after["loudness"]},
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
