"""Assembly and splicing are the parts of the pipeline that run without a GPU,
so they are covered for real: ffmpeg is invoked and the output is probed."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import media
from app.engines.assembly import AssemblyEngine, splice_region
from app.engines.base import EngineRequest


class Ctx:
    job_id = "test-job"

    def log(self, message: str, progress: float | None = None, stage: str = "") -> None:
        pass

    def check_cancelled(self) -> None:
        pass


def make_clip(path: Path, duration: float = 1.2, color: str = "0x1E3A8A") -> Path:
    media.run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"color=c={color}:s=540x960:d={duration}:r=30",
            "-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=48000:duration={duration}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(path),
        ],
        timeout=120,
    )
    return path


@pytest.fixture()
def clips(tmp_path: Path) -> list[dict]:
    first = make_clip(tmp_path / "a.mp4", 1.2, "0x1E3A8A")
    second = make_clip(tmp_path / "b.mp4", 1.0, "0x7A1E1E")
    return [
        {"path": str(first), "duration_s": 1.2, "dialogue": "Premier plan, phrase courte.", "transition": "cut"},
        {"path": str(second), "duration_s": 1.0, "dialogue": "Deuxième plan avec une autre teinte.", "transition": "fade"},
    ]


def test_assembly_produces_vertical_export(tmp_path: Path, clips: list[dict]):
    request = EngineRequest(
        kind="assembly",
        output_dir=tmp_path / "out",
        project={"name": "Test", "format": "9:16"},
        params={"format": "9:16", "fps": 30, "subtitles": True, "transitions": True},
        inputs={"clips": clips},
    )
    output = AssemblyEngine().run(request, Ctx())
    export = next(artifact for artifact in output.artifacts if artifact["kind"] == "export")
    info = media.probe(export["path"])

    assert (info.width, info.height) == (1080, 1920)
    assert abs(info.fps - 30) < 0.5
    assert info.has_audio
    # 1.2 + 1.0 - 0.35 of crossfade
    assert abs(info.duration_s - 1.85) < 0.25

    # subtitles really are burned in: a black-ish frame must contain bright pixels
    import av
    import numpy as np

    container = av.open(export["path"])
    frame = next(container.decode(video=0))
    array = frame.to_ndarray(format="rgb24")
    assert int((array > 200).all(axis=2).sum()) > 400

    srt = next((a for a in output.artifacts if a["kind"] == "subtitles"), None)
    assert srt is not None
    assert "-->" in Path(srt["path"]).read_text(encoding="utf-8")

    poster = next((a for a in output.artifacts if a["kind"] == "poster"), None)
    assert poster is not None


def test_assembly_refuses_missing_clip(tmp_path: Path, clips: list[dict]):
    clips[1]["path"] = str(tmp_path / "does_not_exist.mp4")
    request = EngineRequest(
        kind="assembly", output_dir=tmp_path / "out2", project={"format": "9:16"},
        params={"format": "9:16"}, inputs={"clips": clips},
    )
    with pytest.raises(FileNotFoundError):
        AssemblyEngine().run(request, Ctx())


def test_splice_region_rebuilds_full_clip(tmp_path: Path):
    original = make_clip(tmp_path / "orig.mp4", 3.0)
    replacement = make_clip(tmp_path / "repl.mp4", 1.0, "0x0B1A16")
    out = splice_region(original, replacement, 1.0, 2.0, tmp_path / "spliced.mp4")
    info = media.probe(out)
    assert abs(info.duration_s - 3.0) < 0.35
    assert info.has_audio


def test_assembly_optional_ducking_keeps_audio_and_export(tmp_path: Path, clips: list[dict]):
    """A voiced export may reduce music under dialogue without touching source clips."""
    music = tmp_path / "music.wav"
    media.run_ffmpeg([
        "-f", "lavfi", "-i", "sine=frequency=550:sample_rate=48000:duration=3",
        "-c:a", "pcm_s16le", str(music),
    ])
    request = EngineRequest(
        kind="assembly",
        output_dir=tmp_path / "ducked",
        project={"name": "Pub", "format": "9:16"},
        params={
            "format": "9:16", "fps": 30, "subtitles": False,
            "transitions": False, "music_path": str(music),
            "music_gain_db": -12, "music_ducking": True,
        },
        inputs={"clips": clips},
    )
    output = AssemblyEngine().run(request, Ctx())
    assert output.diagnostics["music_ducking"] is True
    export = next(a for a in output.artifacts if a["kind"] == "export")
    assert media.probe(export["path"]).has_audio
    graph = (request.output_dir / "filtergraph.txt").read_text(encoding="utf-8")
    assert "sidechaincompress=" in graph
    assert "asplit=2[dialogue_bus][duck_key]" in graph


def test_assembly_ducking_requested_without_music_keeps_existing_mix(tmp_path: Path, clips: list[dict]):
    """No music means no compression, even when the option is enabled."""
    request = EngineRequest(
        kind="assembly", output_dir=tmp_path / "no_music",
        project={"name": "Pub", "format": "9:16"},
        params={"format": "9:16", "fps": 30, "subtitles": False,
                "transitions": False, "music_ducking": True},
        inputs={"clips": clips},
    )
    output = AssemblyEngine().run(request, Ctx())
    assert output.diagnostics["music_ducking"] is False
    graph = (request.output_dir / "filtergraph.txt").read_text(encoding="utf-8")
    assert "sidechaincompress=" not in graph
