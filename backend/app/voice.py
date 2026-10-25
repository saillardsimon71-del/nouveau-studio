import copy
import hashlib
import os
import tempfile
import wave
from pathlib import Path

from .ad_references.analysis import _audio_samples, acoustic_metrics, transcript_metrics, transcribe_local
from .ad_references.evaluation import word_error_rate


def inspect_voice(path, expected_text, transcript=None, human_approved=False, speaker_id='', asr_model=None,
                  previous=None, intentions=None):
    path = Path(path)
    with wave.open(str(path), 'rb') as stream:
        duration = stream.getnframes() / stream.getframerate()
    if duration <= 0 or not expected_text.strip():
        raise ValueError('Voix: WAV et dialogue non vides requis')
    model = asr_model or os.environ.get('PVS_ASR_MODEL')
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    previous = previous if previous and previous.get('source_sha256') == source_hash else {}
    evidence = previous.get('asr_evidence')
    if previous.get('transcription_source') == 'whisper_local_cpu':
        evidence = {key: previous[key] for key in ('source_sha256', 'asr_model', 'transcript', 'voice')}
    method = 'not_performed'
    voice = {'speech_present': None, 'limitations': ['Transcription et écoute requises']}
    if transcript is not None:
        method = 'human_transcript' if human_approved else 'supplied_transcript'
        voice = {'transcript': transcript, 'speech_present': bool(transcript.strip()),
                 'limitations': ['Transcription fournie sans alignement temporel']}
        if evidence and word_error_rate(evidence['transcript'], transcript) == 0:
            voice = copy.deepcopy(evidence['voice'])
            voice['transcript'] = transcript
    elif model:
        result = transcribe_local(path, model, 'fr')
        voice = transcript_metrics(result, duration)
        method = 'whisper_local_cpu'
    with tempfile.TemporaryDirectory(prefix='voice-qc-') as temp:
        samples, _ = _audio_samples(path, Path(temp))
        audio = acoustic_metrics(samples, voice, speech_only=bool(voice.get('segments')))
    observed = voice.get('transcript')
    wer = word_error_rate(expected_text, observed) if observed is not None else None
    active = audio['rms_dbfs'] > -60
    return {'source_sha256': source_hash,
            'expected_text': expected_text, 'duration_s': duration, 'speaker_id': speaker_id,
            'transcript': observed, 'transcription_source': method,
            'asr_model': Path(model).name if method == 'whisper_local_cpu' else None,
            'asr_evidence': evidence, 'intentions': intentions or previous.get('intentions') or {},
            'text_match': {'word_error_rate': wer, 'matches': wer == 0},
            'voice': voice, 'audio': audio, 'human_approved': human_approved,
            'accepted': bool(human_approved and wer == 0 and active),
            'human_review': {key: {'score': None, 'evidence': None} for key in
                             ('voice_naturalness', 'intonation', 'lip_sync', 'facial_expression', 'gesture', 'credibility')}}


def require_validated_voice(path, expected_text, report):
    if not report or report.get('expected_text') != expected_text:
        raise ValueError('Voix: dialogue modifié ou prestation non vérifiée')
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != report.get('source_sha256'):
        raise ValueError('Voix: fichier modifié depuis sa validation')
    if not report.get('accepted') or not report.get('human_approved'):
        raise ValueError('Voix: transcription exacte et écoute approuvée requises avant animation')
    if word_error_rate(expected_text, report.get('transcript') or '') != 0:
        raise ValueError('Voix: paroles manquantes, répétées ou supplémentaires')
    return report


def selected_voice(shot, params=None):
    from . import db
    values = {**(shot.get('params') or {}), **(params or {})}
    artifact = db.get('artifacts', values.get('audio_artifact_id', ''))
    if not artifact or artifact.get('shot_id') != shot['id'] or artifact.get('kind') != 'audio':
        raise ValueError('Voix: sélectionner et valider un WAV appartenant à ce plan')
    report = require_validated_voice(artifact['path'], shot.get('dialogue', ''),
                                     (artifact.get('meta') or {}).get('performance'))
    return artifact, report
