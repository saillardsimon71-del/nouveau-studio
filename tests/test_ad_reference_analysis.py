import json
import math
from pathlib import Path

import pytest

from app import media
from app.ad_references.analysis import analyze, transcript_metrics
from app.ad_references.evaluation import compare, evaluate, word_error_rate
from app.ad_references.library import derive_recipe, Library


def test_word_metrics_merge_overlaps_and_distinguish_rates():
    transcript = {"language": "fr", "segments": [
        {"start": 0, "end": 2, "text": "Bonjour tout le monde.", "words": [
            {"word": "Bonjour", "start": 0, "end": .4},
            {"word": "tout", "start": .4, "end": .8},
            {"word": "le", "start": .8, "end": 1},
            {"word": "monde.", "start": 1, "end": 2}]},
        {"start": 1.8, "end": 3, "text": "Très bien."},
        {"start": 4, "end": 5, "text": "Au revoir."}]}
    result = transcript_metrics(transcript, 8)
    assert result["word_count"] == 8
    assert result["speech_span_s"] == 4
    assert result["words_per_minute_speech_span"] == 120
    assert result["words_per_minute_clip"] == 60
    assert result["word_timing_coverage"] == .5
    assert result["pauses"] == [{"start_s": 3, "end_s": 4, "duration_s": 1}]


def test_bad_timestamps_are_rejected():
    for start, end in [(2, 1), (-1, 2), (0, 11), (0, math.nan)]:
        with pytest.raises(ValueError):
            transcript_metrics({"segments": [{"start": start, "end": end, "text": "Bonjour"}]}, 10)


def make_media(path, audio=True):
    args = ["-f", "lavfi", "-i", "color=red:s=160x240:r=24:d=1.5",
            "-f", "lavfi", "-i", "color=blue:s=160x240:r=24:d=1.5"]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=220:duration=3:sample_rate=16000"]
    args += ["-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]"]
    if audio:
        args += ["-map", "2:a", "-c:a", "aac"]
    media.run_ffmpeg([*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])
    return path


def test_real_cpu_analysis_cuts_audio_and_rights_gate(tmp_path):
    path = make_media(tmp_path / "clip.mp4")
    with pytest.raises(ValueError, match="authorized"):
        analyze(path, tmp_path / "denied", authorization="")
    result = analyze(path, tmp_path / "analysis", authorization="test fixture created locally")
    assert result["source"]["sha256"]
    assert len(result["visual"]["shots"]) == 2
    assert abs(result["visual"]["shots"][0]["end_s"] - 1.5) < .1
    assert all(Path(f["path"]).is_file() for f in result["visual"]["frames"])
    assert result["voice"]["speech_present"] is None
    assert result["voice"]["pitch"] is None
    assert result["voice"]["word_count"] is None
    assert result["audio"]["rms_dbfs"] is not None
    assert result["visual"]["semantic_analysis"] == "not_performed"
    assert json.loads((tmp_path / "analysis" / "analysis.json").read_text()) == result


def test_no_audio_is_not_missing_transcription(tmp_path):
    path = make_media(tmp_path / "silent.mp4", audio=False)
    result = analyze(path, tmp_path / "out", authorization="original fixture")
    assert result["voice"]["speech_present"] is False
    assert result["voice"]["word_count"] == 0
    assert result["voice"]["pitch"] is None


def test_word_error_rate_and_unavailable_comparison():
    assert word_error_rate("Bonjour le monde", "bonjour monde") == pytest.approx(1 / 3)
    assert word_error_rate("", "") is None
    report = {"schema_version": "1.0", "source": {"sha256": "x"}, "duration_seconds": 5,
              "analysis_config": {}, "voice": {"speech_present": None, "word_count": None},
              "visual": {"shots": [], "semantic_analysis": "not_performed"}}
    result = evaluate(report, expected_dialogue="Bonjour")
    assert result["transcript_match"]["word_error_rate"] is None
    assert result["human_review"]["lip_sync"]["status"] == "pending"
    comparison = compare(result, result)
    assert comparison["deltas"]["words_per_minute_clip"] is None
    assert comparison["quality_winner"] is None


def test_supplied_transcript_requires_alignment_provenance(tmp_path):
    path = make_media(tmp_path / "clip.mp4")
    result = analyze(path, tmp_path / "out", authorization="fixture", transcript={
        "language": "fr", "segments": [{"start": .2, "end": 2, "text": "Bonjour à vous."}]})
    assert result["voice"]["transcription_source"] == "supplied_transcript_unverified"
    assert result["analysis_config"]["transcription_method"] == "supplied_transcript_unverified"
    assert result["voice"]["pitch"] is None


def test_measured_recipe_needs_real_observation_and_authorization():
    reference = Library().references[0].model_dump()
    with pytest.raises(ValueError, match="authorized"):
        derive_recipe(reference, "recipe", "Test")
    reference["source"].update(analysis_access="full_video", media_authorized=True,
                                authorization_evidence="own file")
    reference["observations"] = [{"id": "eye", "domain": "visual", "value": "Look at camera during opening",
        "basis": "video_observation", "confidence": .8,
        "evidence": {"locator": "frame1.jpg", "start_s": 0, "end_s": 1, "media_sha256": "a" * 64}}]
    recipe = derive_recipe(reference, "recipe", "Test")
    assert recipe.basis == "analyzed_media"
    assert recipe.rules[0]["observation_id"] == "eye"


def test_speech_only_pitch_and_energy_are_measured_on_voiced_fixture(tmp_path):
    pytest.importorskip("librosa")
    from app.ad_references.analysis import acoustic_metrics
    import numpy as np
    t = np.arange(32000) / 16000
    samples = .2 * np.sin(2 * np.pi * (140 * t + 15 * t ** 2))
    voice = transcript_metrics({"segments": [{"start": 0, "end": 2, "text": "Bonjour."}]}, 2)
    acoustic_metrics(samples, voice, speech_only=True)
    assert 145 < voice["pitch"]["median_hz"] < 200
    assert voice["pitch"]["p10_p90_semitones"] > 1
    assert voice["vocal_energy"]["contour"]


def test_local_asr_never_downloads_missing_models(tmp_path):
    from app.ad_references.analysis import transcribe_local
    with pytest.raises(ValueError, match="local .pt"):
        transcribe_local(tmp_path / "file.wav", tmp_path / "absent.pt")
