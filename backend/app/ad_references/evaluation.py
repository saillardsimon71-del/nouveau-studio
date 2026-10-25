from ..qc import HUMAN_CHECKS
from .performance import words


def word_error_rate(expected, observed):
    target, actual = words(expected.lower()), words(observed.lower())
    if not target:
        return None
    previous = list(range(len(actual) + 1))
    for i, token in enumerate(target, 1):
        row = [i]
        for j, other in enumerate(actual, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (token != other)))
        previous = row
    return round(previous[-1] / len(target), 6)


def evaluate(analysis, expected_dialogue="", scene_id="", version=""):
    voice, visual = analysis["voice"], analysis["visual"]
    transcript = voice.get("transcript")
    return {"schema_version": "1.0", "scene_id": scene_id, "version": version,
            "source": analysis["source"], "duration_seconds": analysis["duration_seconds"],
            "analysis_config": analysis["analysis_config"],
            "transcript_match": {"expected": expected_dialogue, "observed": transcript,
                                 "word_error_rate": word_error_rate(expected_dialogue, transcript)
                                 if transcript is not None else None,
                                 "basis": voice.get("transcription_source", "no_asr")},
            "metrics": {"speech_present": voice.get("speech_present"),
                        "word_count": voice.get("word_count"),
                        "words_per_minute_clip": voice.get("words_per_minute_clip"),
                        "words_per_minute_speech_span": voice.get("words_per_minute_speech_span"),
                        "speech_span_s": voice.get("speech_span_s"),
                        "pause_count": len(voice["pauses"]) if "pauses" in voice else None,
                        "pitch_p10_p90_semitones": (voice.get("pitch") or {}).get("p10_p90_semitones"),
                        "shot_count": visual.get("shot_count"),
                        "shot_durations_s": [s["duration_s"] for s in visual.get("shots", [])]},
            "observations": analysis.get("observations", []),
            "human_review": {key: {"status": "pending", "evidence": None} for key in
                             ("lip_sync", "acting_naturalness", "visual_continuity", "product_presence", "facial_expression", "obvious_defects")},
            "human_checklist": HUMAN_CHECKS,
            "limitations": analysis.get("limitations", [])}


def compare(baseline, candidate):
    if baseline["schema_version"] != candidate["schema_version"]:
        raise ValueError("incompatible evaluation schema versions")
    if baseline.get("scene_id") != candidate.get("scene_id"):
        raise ValueError("comparisons require the same scene_id")
    compatible = baseline["analysis_config"] == candidate["analysis_config"]
    metrics = {}
    for key in ("word_count", "words_per_minute_clip", "words_per_minute_speech_span", "speech_span_s",
                "pause_count", "pitch_p10_p90_semitones", "shot_count"):
        a, b = baseline["metrics"].get(key), candidate["metrics"].get(key)
        metrics[key] = round(b - a, 3) if compatible and a is not None and b is not None else None
    return {"scene_id": baseline.get("scene_id"), "baseline_version": baseline.get("version"),
            "candidate_version": candidate.get("version"), "comparable_config": compatible,
            "same_expected_dialogue": baseline["transcript_match"]["expected"] == candidate["transcript_match"]["expected"],
            "deltas": metrics, "quality_winner": None,
            "limitations": ["A positive delta is not a quality improvement. Listen and inspect both versions.",
                             "Reanalyze with identical configuration when comparable_config is false."]}
