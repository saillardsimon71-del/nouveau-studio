import io
import wave

import numpy as np
import pytest

from app.ad_references.library import Library
from app.ad_references.performance import enrich_storyboard
from app.schemas import ShotSpec, Storyboard


def wav_file(path, seconds=1):
    samples = (.15 * np.sin(2 * np.pi * 180 * np.arange(int(16000 * seconds)) / 16000) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(samples.tobytes())
    return path


def test_reference_enrichment_preserves_avatar_and_explicit_engine():
    shot = ShotSpec(kind='avatar', duration_s=3, dialogue='Bonjour à vous.',
                    engine_hint='modal_avatar', character_id='selected_actor', performance={'intent': 'curiosity'})
    result = enrich_storyboard(Storyboard(shots=[shot]), Library().retrieve('UGC cosmétique'))
    assert result.shots[0].kind == 'avatar'
    assert result.shots[0].engine_hint == 'modal_avatar'
    assert result.shots[0].performance['intent'] == 'curiosity'
    assert result.shots[0].character_id == 'selected_actor'
    assert 'curiosity' in result.shots[0].prompt


def test_selected_audio_routes_stale_h3_presenter_to_avatar():
    from app.engines.registry import route_shot
    shot = {'kind': 'b_roll', 'dialogue': 'Bonjour.',
            'params': {'engine_hint': 'modal_h3', 'audio_artifact_id': 'art_voice'}}
    assert route_shot(shot, {}) == ('avatar', None, 'voice_first')


def test_silent_shot_does_not_route_to_tts_or_avatar():
    from app.engines.registry import route_shot
    assert route_shot({'kind': 'product', 'dialogue': '', 'params': {}}, {}) == ('video', None, 'legacy')


def test_explicit_native_mode_keeps_existing_h3_projects():
    from app.engines.registry import route_shot
    shot = {'kind': 'b_roll', 'dialogue': 'Bonjour.', 'voice_id': 'voice_old',
            'params': {'performance_mode': 'native', 'engine_hint': 'modal_h3'}}
    assert route_shot(shot, {}) == ('video', 'modal_h3', 'native')


def test_external_audio_cannot_be_sent_to_explicit_native_engine():
    from app.engines.registry import route_shot
    with pytest.raises(ValueError, match='audio'):
        route_shot({'kind': 'avatar', 'dialogue': 'Bonjour.', 'params': {'audio_artifact_id': 'art_v'}}, {}, 'modal_h3')


def test_voice_report_rejects_extra_or_missing_words(tmp_path):
    from app.voice import inspect_voice
    path = wav_file(tmp_path / 'source.wav')
    report = inspect_voice(path, 'Bonjour à vous.', transcript='Bonjour à vous et bienvenue.', human_approved=True)
    assert report['accepted'] is False
    assert report['text_match']['word_error_rate'] > 0
    assert report['source_sha256']
    assert report['duration_s'] == 1


def test_exact_asr_text_without_perceptive_approval_is_not_validated(tmp_path):
    from app.voice import inspect_voice
    report = inspect_voice(wav_file(tmp_path / 'source.wav'), 'Bonjour.', transcript='Bonjour.')
    assert report['text_match']['word_error_rate'] == 0
    assert report['accepted'] is False


def test_voice_validation_is_bound_to_file_and_dialogue(tmp_path):
    from app.voice import inspect_voice, require_validated_voice
    path = wav_file(tmp_path / 'source.wav')
    report = inspect_voice(path, 'Bonjour.', transcript='Bonjour.', human_approved=True)
    require_validated_voice(path, 'Bonjour.', report)
    with pytest.raises(ValueError, match='dialogue'):
        require_validated_voice(path, 'Bonsoir.', report)
    wav_file(path, seconds=.8)
    with pytest.raises(ValueError, match='modifié'):
        require_validated_voice(path, 'Bonjour.', report)


def test_silent_wav_cannot_be_approved(tmp_path):
    from app.voice import inspect_voice
    path = tmp_path / 'silence.wav'
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\x00\x00' * 16000)
    assert not inspect_voice(path, 'Bonjour.', transcript='Bonjour.', human_approved=True)['accepted']


def test_audio_review_is_owned_by_shot_and_selects_voice_first(client, project, tmp_path):
    shot = client.post(f"/api/projects/{project['id']}/shots", json={
        'kind': 'avatar', 'dialogue': 'Bonjour.', 'prompt': 'Presenter', 'duration_s': 5}).json()
    path = wav_file(tmp_path / 'source.wav')
    artifact = client.post(f"/api/shots/{shot['id']}/upload?kind=audio", files={
        'file': ('source.wav', io.BytesIO(path.read_bytes()), 'audio/wav')}).json()
    response = client.post(f"/api/shots/{shot['id']}/voice/{artifact['id']}/review", json={
        'transcript': 'Bonjour.', 'human_approved': True, 'speaker_id': 'speaker_demo'})
    assert response.status_code == 200, response.text
    assert response.json()['meta']['performance']['accepted'] is True
    updated = client.get(f"/api/projects/{project['id']}").json()['shots'][0]
    assert updated['duration_s'] == 1
    assert updated['params']['performance_mode'] == 'voice_first'
    assert updated['params']['audio_artifact_id'] == artifact['id']
    other = client.post(f"/api/projects/{project['id']}/shots", json={'kind': 'avatar'}).json()
    assert client.post(f"/api/shots/{other['id']}/voice/{artifact['id']}/review", json={
        'transcript': 'Bonjour.', 'human_approved': True}).status_code == 400


def test_voice_first_generation_without_validated_audio_is_blocked_before_enqueue(client, project):
    shot = client.post(f"/api/projects/{project['id']}/shots", json={
        'kind': 'avatar', 'dialogue': 'Bonjour.', 'prompt': 'Presenter'}).json()
    client.patch(f"/api/shots/{shot['id']}", json={'params': {'performance_mode': 'voice_first'}})
    response = client.post(f"/api/shots/{shot['id']}/generate", json={})
    assert response.status_code == 400
    assert client.get(f"/api/jobs?project_id={project['id']}").json() == []


def test_human_review_retains_asr_timing_and_intentions(tmp_path, monkeypatch):
    from app import voice
    monkeypatch.setattr(voice, 'transcribe_local', lambda *args: {
        'language': 'fr', 'segments': [{'start': .1, 'end': .4, 'text': 'Bonjour.'},
                                       {'start': .7, 'end': .9, 'text': 'Merci.'}]})
    path = wav_file(tmp_path / 'source.wav')
    initial = voice.inspect_voice(path, 'Bonjour. Merci.', asr_model='small.pt')
    reviewed = voice.inspect_voice(path, 'Bonjour. Merci.', transcript='Bonjour. Merci.',
                                   human_approved=True, previous=initial, intentions={'intent': 'reassuring'})
    assert reviewed['accepted']
    assert reviewed['voice']['pauses'][0]['duration_s'] == .3
    assert reviewed['asr_evidence']['asr_model'] == 'small.pt'
    assert reviewed['intentions'] == {'intent': 'reassuring'}


def test_queued_job_revalidates_voice_before_resolving_engine(client, project, monkeypatch):
    from app import jobs
    shot = client.post(f"/api/projects/{project['id']}/shots", json={
        'kind': 'avatar', 'dialogue': 'Bonjour.', 'prompt': 'Presenter'}).json()
    client.patch(f"/api/shots/{shot['id']}", json={'params': {'performance_mode': 'voice_first'}})
    monkeypatch.setattr(jobs.registry, 'resolve', lambda *args: pytest.fail('Engine contacted before validation'))
    with pytest.raises(ValueError, match='WAV'):
        jobs._dispatch({'type': 'avatar', 'shot_id': shot['id'], 'project_id': project['id'], 'params': {}}, None)


def test_assembly_rejects_video_from_different_voice(client, project, tmp_path, monkeypatch):
    from app import db, jobs
    from app.voice import inspect_voice
    shot = client.post(f"/api/projects/{project['id']}/shots", json={
        'kind': 'avatar', 'dialogue': 'Bonjour.', 'prompt': 'Presenter'}).json()
    path = wav_file(tmp_path / 'source.wav')
    report = inspect_voice(path, 'Bonjour.', transcript='Bonjour.', human_approved=True)
    audio = db.insert('artifacts', {'id': db.new_id('art'), 'shot_id': shot['id'], 'project_id': project['id'],
        'kind': 'audio', 'path': str(path), 'mime': 'audio/wav', 'created_at': db.now_iso(),
        'meta': {'performance': report}})
    video = db.insert('artifacts', {'id': db.new_id('art'), 'shot_id': shot['id'], 'project_id': project['id'],
        'kind': 'video', 'path': str(tmp_path / 'old.mp4'), 'mime': 'video/mp4', 'created_at': db.now_iso(),
        'meta': {'source_audio_sha256': 'outdated'}})
    db.update('shots', shot['id'], {'params': {'performance_mode': 'voice_first', 'audio_artifact_id': audio['id']},
                                   'selected_artifact': video['id']})
    monkeypatch.setattr(jobs.AssemblyEngine, 'run', lambda *args: pytest.fail('Assembly started with outdated voice'))
    with pytest.raises(ValueError, match='voix'):
        jobs._run_assembly({'id': 'diagnostic'}, {}, project, None)


def test_new_upload_replaces_selected_voice_and_requires_fresh_review(client, project, tmp_path):
    shot = client.post(f"/api/projects/{project['id']}/shots", json={
        'kind': 'avatar', 'dialogue': 'Bonjour.', 'prompt': 'Presenter'}).json()
    path = wav_file(tmp_path / 'source.wav')
    for _ in range(2):
        artifact = client.post(f"/api/shots/{shot['id']}/upload?kind=audio", files={
            'file': ('source.wav', path.read_bytes(), 'audio/wav')}).json()
        updated = client.get(f"/api/projects/{project['id']}").json()['shots'][0]
        assert updated['params']['audio_artifact_id'] == artifact['id']
        assert updated['status'] == 'voice_review'
        assert client.post(f"/api/shots/{shot['id']}/generate", json={}).status_code == 400
        assert client.post(f"/api/shots/{shot['id']}/voice/{artifact['id']}/review", json={
            'transcript': 'Bonjour.', 'human_approved': True}).status_code == 200


def test_new_avatar_demo_requires_voice_review_before_animation(client):
    project = client.post('/api/projects/avatar-demo').json()
    shot = project['shots'][0]
    assert shot['params']['performance_mode'] == 'voice_first'
    assert client.post(f"/api/shots/{shot['id']}/generate", json={}).status_code == 400
