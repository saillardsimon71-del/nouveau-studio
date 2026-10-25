import base64
from pathlib import Path

import pytest

from app.engines.base import EngineRequest
from test_voice_first import wav_file


@pytest.mark.parametrize('duration,segments,frames', [(3.72, 1, 93), (6.4, 2, 160), (6.92, 2, 173)])
def test_continuation_uses_source_duration_and_context_overlap(duration, segments, frames):
    from backend.app.avatar import plan_audio
    result = plan_audio(duration, max_segments=2)
    assert result['num_segments'] == segments
    assert result['output_frames'] == frames
    assert result['generation_frames'] == (93 if segments == 1 else 173)


def test_one_segment_deployment_still_rejects_long_audio():
    from backend.app.avatar import plan_audio
    with pytest.raises(ValueError, match='3.72'):
        plan_audio(4, max_segments=1)


@pytest.mark.parametrize('duration', [0, -1, 6.93, float('nan'), float('inf')])
def test_invalid_voice_duration_never_reaches_gpu(duration):
    from backend.app.avatar import plan_audio
    with pytest.raises(ValueError):
        plan_audio(duration, max_segments=2)


def test_modal_two_segment_payload_requires_explicit_deployment_capability(tmp_path, monkeypatch):
    from app.engines.modal_remote import ModalEngine
    monkeypatch.setenv('PVS_MODAL_AVATAR_MAX_SEGMENTS', '2')
    path = wav_file(tmp_path / 'speech.wav', 6.4)
    photo = Path(__file__).resolve().parents[1] / 'benchmark_assets/character_reference.png'
    request = EngineRequest(kind='avatar', output_dir=tmp_path / 'request',
                            inputs={'audio_path': str(path), 'reference_image': str(photo)})
    payload = ModalEngine('avatar').payload(request)
    assert len(payload) == 4
    assert payload[3] == 2
    assert base64.b64decode(payload[1]) == path.read_bytes()


def test_output_selection_cannot_choose_first_segment_for_continuation(tmp_path):
    from backend.app.avatar import select_output
    (tmp_path / 'ai2v_demo_1.mp4').write_bytes(b'first')
    with pytest.raises(ValueError, match='continuation'):
        select_output(tmp_path, 2)
    final = tmp_path / 'video_continue_2.mp4'
    final.write_bytes(b'continued')
    assert select_output(tmp_path, 2) == final


def test_diagnostic_inputs_require_audio_approval_before_remote_call(tmp_path):
    import json
    from app.avatar import diagnostic_inputs
    from app.voice import inspect_voice
    path = wav_file(tmp_path / 'speech.wav', 1)
    photo = Path(__file__).resolve().parents[1] / 'benchmark_assets/character_reference.png'
    report = inspect_voice(path, 'Bonjour.', transcript='Bonjour.')
    report_path = tmp_path / 'voice.json'
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='écoute'):
        diagnostic_inputs(photo, path, report_path, 2)
    report.update(accepted=True, human_approved=True)
    report_path.write_text(json.dumps(report))
    image, audio, plan = diagnostic_inputs(photo, path, report_path, 2)
    assert audio == path.read_bytes()
    assert image == photo.read_bytes()
    assert plan['num_segments'] == 1


def test_worker_mounts_helper_module_needed_during_container_import(monkeypatch):
    import importlib
    import modal
    mounted = []
    original = modal.Image.add_local_python_source

    def capture(self, *modules, **kwargs):
        mounted.extend(modules)
        return original(self, *modules, **kwargs)

    monkeypatch.setattr(modal.Image, 'add_local_python_source', capture)
    module = importlib.import_module('deploy.modal_avatar_worker')
    importlib.reload(module)
    assert 'backend' in mounted
