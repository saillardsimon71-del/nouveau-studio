import hashlib
import importlib.metadata
import json
import math
import re
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .. import media
from .models import Observation
from .performance import words


def _intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def transcript_metrics(transcript, duration):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid media duration")
    segments = transcript.get("segments", [])
    if not isinstance(segments, list):
        raise ValueError("transcript segments must be a list")
    spans, timed_words, texts = [], [], []
    normalized = []
    for segment in segments:
        start, end = float(segment["start"]), float(segment["end"])
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= duration + .05:
            raise ValueError("invalid segment timestamps")
        text = segment.get("text", "").strip()
        if not text:
            continue
        texts.append(text)
        spans.append((start, min(end, duration)))
        normalized.append({"start_s": start, "end_s": end, "text": text,
                           "speaker": segment.get("speaker"), "confidence": segment.get("avg_logprob")})
        for word in segment.get("words", []):
            if word.get("start") is None or word.get("end") is None:
                continue
            ws, we = float(word["start"]), float(word["end"])
            if not all(math.isfinite(v) for v in (ws, we)) or not start - .05 <= ws < we <= end + .05:
                raise ValueError("invalid word timestamps")
            token = word.get("word", "").strip()
            timed_words.append({"word": token, "start_s": ws, "end_s": we,
                                "confidence": word.get("score", word.get("probability")),
                                "speaker": word.get("speaker", segment.get("speaker"))})
    count = len(words(" ".join(texts)))
    merged = _intervals(spans)
    speech_span = sum(end - start for start, end in merged)
    gaps = [{"start_s": end, "end_s": start, "duration_s": round(start - end, 3)}
            for (_, end), (start, _) in zip(merged, merged[1:]) if start - end >= .2]
    covered = sum(len(words(w["word"])) for w in timed_words)
    articulation = sum(e - s for s, e in _intervals([(w["start_s"], w["end_s"]) for w in timed_words]))
    sentence_pauses = [{"start_s": a["end_s"], "end_s": b["start_s"],
                        "duration_s": round(b["start_s"] - a["end_s"], 3)}
                       for a, b in zip(timed_words, timed_words[1:])
                       if re.search(r"[.!?]$", a["word"]) and b["start_s"] >= a["end_s"]]
    return {"language": transcript.get("language"), "speech_present": bool(count),
            "transcript": " ".join(texts), "segments": normalized, "words": timed_words,
            "word_count": count, "speech_span_s": round(speech_span, 3),
            "words_per_minute_clip": round(count * 60 / duration, 2),
            "words_per_minute_speech_span": round(count * 60 / speech_span, 2) if speech_span else None,
            "word_timing_coverage": min(1, covered / count) if count else 0,
            "word_articulation_s": round(articulation, 3) if count and covered == count else None,
            "pauses": gaps, "pause_basis": "gaps_between_asr_segments_not_sentence_boundaries",
            "sentence_pauses": sentence_pauses if covered == count and count else None,
            "segment_pace": [{"start_s": s["start_s"], "end_s": s["end_s"],
                              "wpm": round(len(words(s["text"])) * 60 / (s["end_s"] - s["start_s"]), 2)}
                             for s in normalized],
            "pitch": None, "vocal_energy": None,
            "limitations": ["ASR is fallible. Segment spans include internal pauses; speaker overlap affects WPM.",
                            "Breathing, emotion, accent and vocal intention require listening or labeled inference."]}


def transcribe_local(path, model_path, language="fr"):
    model_path = Path(model_path)
    if not model_path.is_file() or model_path.suffix != ".pt":
        raise ValueError("Whisper requires an existing local .pt checkpoint; no model download")
    import whisper

    model = whisper.load_model(str(model_path.resolve()), device="cpu")
    result = model.transcribe(str(path), language=language, fp16=False, word_timestamps=True,
                              condition_on_previous_text=False, temperature=0)
    return result


def detect_shots(path, duration, threshold=.3):
    if not 0 < threshold < 1:
        raise ValueError("scene threshold must be between 0 and 1")
    proc = subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(path),
                           "-vf", f"select=gt(scene\\,{threshold}),showinfo", "-an", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=600)
    if proc.returncode:
        raise media.MediaError(proc.stderr[-1500:])
    cuts = sorted({round(float(t), 4) for t in re.findall(r"pts_time:([\d.]+)", proc.stderr)
                   if .05 < float(t) < duration - .05})
    boundaries = [0.0, *cuts, duration]
    return [{"shot_id": f"shot_{i+1:03}", "start_s": start, "end_s": end,
             "duration_s": round(end - start, 4), "boundary_method": "ffmpeg_scene_score",
             "transition": "cut_candidate" if i else "start", "confidence": None}
            for i, (start, end) in enumerate(zip(boundaries, boundaries[1:]))]


def _audio_samples(path, temp):
    wav_path = temp / "audio.wav"
    media.run_ffmpeg(["-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path)])
    with wave.open(str(wav_path), "rb") as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float) / 32768
    return samples, wav_path


def acoustic_metrics(samples, voice, speech_only):
    rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0
    audio = {"rms_dbfs": round(20 * math.log10(max(rms, 1e-12)), 3),
             "scope": "isolated_speech_declared_by_operator" if speech_only else "mixed_soundtrack",
             "sample_rate": 16000}
    if not speech_only or not voice.get("speech_present"):
        return audio
    try:
        import librosa
    except ImportError:
        voice["limitations"].append("librosa absent: no pitch or vocal energy contour")
        return audio
    contours, energy = [], []
    for start, end in _intervals([(s["start_s"], s["end_s"]) for s in voice["segments"]]):
        y = samples[int(start * 16000):int(end * 16000)]
        if len(y) < 1024:
            continue
        f0, voiced, probability = librosa.pyin(y, fmin=60, fmax=500, sr=16000, frame_length=1024, hop_length=256)
        intensity = librosa.feature.rms(y=y, frame_length=1024, hop_length=256)[0]
        db = 20 * np.log10(np.maximum(intensity, 1e-12))
        energy.extend({"time_s": round(start + i * 256 / 16000, 3), "rms_dbfs": round(float(v), 2)}
                      for i, v in enumerate(db))
        for i, value in enumerate(f0):
            if voiced[i] and np.isfinite(value) and probability[i] >= .5:
                contours.append({"time_s": round(start + i * 256 / 16000, 3),
                                 "f0_hz": round(float(value), 2), "voiced_probability": round(float(probability[i]), 3)})
    values = np.array([v["f0_hz"] for v in contours])
    voice["pitch"] = {"method": "librosa.pyin", "fmin_hz": 60, "fmax_hz": 500,
                       "median_hz": round(float(np.median(values)), 2) if values.size else None,
                       "p10_p90_semitones": round(float(12 * np.log2(np.percentile(values, 90) /
                                                                        np.percentile(values, 10))), 2) if values.size else None,
                       "contour": contours}
    db_values = [v["rms_dbfs"] for v in energy]
    voice["vocal_energy"] = {"method": "RMS in ASR speech spans, dBFS; not perceived loudness", "contour": energy,
                              "p10_p90_db": round(float(np.percentile(db_values, 90) - np.percentile(db_values, 10)), 2)
                              if db_values else None}
    trends = []
    for segment in voice["segments"]:
        points = [v["f0_hz"] for v in contours if segment["start_s"] <= v["time_s"] <= segment["end_s"]]
        if len(points) < 9:
            continue
        third = len(points) // 3
        delta = 12 * math.log2(float(np.median(points[-third:])) / float(np.median(points[:third])))
        trends.append({"start_s": segment["start_s"], "end_s": segment["end_s"],
                       "delta_semitones": round(delta, 2),
                       "direction": "rising" if delta > 1 else "falling" if delta < -1 else "level"})
    voice["intonation_trends"] = {"method": "median F0 in first/last third of each ASR segment", "segments": trends}
    voice["emphasis_candidates"] = [v for v in energy if db_values and v["rms_dbfs"] >= float(np.median(db_values)) + 4]
    voice["limitations"].append("pYIN can make octave errors; mixed speakers are not separated. Trends are not emotions.")
    return audio


def analyze(path, output_dir, authorization, transcript=None, whisper_model=None, language="fr",
            speech_only=False, scene_threshold=.3, observations=None):
    if not authorization.strip():
        raise ValueError("Media must be authorized; record authorization evidence")
    path, output_dir = Path(path).resolve(), Path(output_dir).resolve()
    if not path.is_file():
        raise ValueError("a local authorized media file is required")
    info = media.probe(path)
    if not 0 < info.duration_s <= 600 or not info.width:
        raise ValueError("analysis requires a video of at most 600 seconds")
    if transcript is not None and whisper_model is not None:
        raise ValueError("choose supplied transcript OR local ASR")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    sha = digest.hexdigest()
    shots = detect_shots(path, info.duration_s, scene_threshold)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for shot in shots[:80]:
        timestamp = round((shot["start_s"] + shot["end_s"]) / 2, 3)
        frame = output_dir / f"{shot['shot_id']}.jpg"
        media.run_ffmpeg(["-ss", str(timestamp), "-i", str(path), "-frames:v", "1", "-vf", "scale=512:-2", str(frame)])
        frames.append({"shot_id": shot["shot_id"], "time_s": timestamp, "path": str(frame)})
    validated = []
    for value in observations or []:
        observation = Observation.model_validate(value)
        if observation.basis == "source_description":
            raise ValueError("media annotations need timed evidence")
        if observation.evidence.media_sha256 != sha or observation.evidence.end_s > info.duration_s:
            raise ValueError("observation evidence does not match analyzed media")
        validated.append(observation.model_dump())
    voice = {"speech_present": None, "word_count": None, "pitch": None, "vocal_energy": None,
             "limitations": ["No ASR performed: audio presence does not establish speech presence."]}
    audio = {"present": info.has_audio}
    if info.has_audio:
        with tempfile.TemporaryDirectory(prefix="ad-analysis-") as temp:
            samples, wav_path = _audio_samples(path, Path(temp))
            if whisper_model is not None:
                transcript = transcribe_local(wav_path, whisper_model, language)
            if transcript is not None:
                voice = transcript_metrics(transcript, info.duration_s)
                voice["transcription_source"] = "whisper_local_cpu" if whisper_model else "supplied_transcript_unverified"
            audio.update(acoustic_metrics(samples, voice, speech_only))
    else:
        if transcript is not None:
            raise ValueError("cannot attach a transcript to media without audio")
        voice = transcript_metrics({"segments": [], "language": None}, info.duration_s)
    result = {"schema_version": "1.0", "source": {"path": str(path), "sha256": sha,
              "authorization_evidence": authorization, "analysis_access": "full_video"},
              "duration_seconds": info.duration_s, "media": info.to_dict(),
              "analysis_config": {"scene_threshold": scene_threshold, "speech_only": speech_only,
                                  "asr_model": Path(whisper_model).name if whisper_model else None,
                                  "asr_model_sha256": _file_hash(whisper_model) if whisper_model else None,
                                  "language": language, "ffmpeg": media.ffmpeg_version(),
                                  "transcription_method": voice.get("transcription_source", "not_performed"),
                                  "packages": _package_versions()},
              "audio": audio, "voice": voice,
              "visual": {"shots": shots, "shot_count": len(shots), "frames": frames,
                         "semantic_analysis": "annotations_imported" if validated else "not_performed"},
              "observations": validated,
              "limitations": ["Scene threshold produces cut candidates; fades and movement can cause errors.",
                               "Midpoint frames do not establish continuous actions or lip synchronization.",
                               "No automatic face, gaze, gesture, product, camera or marketing inference was run."]}
    media.write_json(output_dir / "analysis.json", result)
    return result


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_versions():
    versions = {}
    for name in ("av", "numpy", "openai-whisper", "librosa"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions
