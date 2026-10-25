import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("engine", ["chatterbox", "voxcpm"])
def test_tts_uses_selected_checkpoint_and_supported_generation_api(engine, tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "gpu" / f"tts_{engine}.py"
    spec = importlib.util.spec_from_file_location(f"tts_{engine}_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [str(script), "--text", "Bonjour.", "--out", str(tmp_path / "v.wav")])
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True)))
    if engine == "chatterbox":
        def load(*, device, t3_model="v2"):
            assert t3_model == "v3"
            return SimpleNamespace(sr=24000, generate=lambda text, **kwargs: [0.0])
        monkeypatch.setitem(sys.modules, "chatterbox.mtl_tts", SimpleNamespace(
            ChatterboxMultilingualTTS=SimpleNamespace(from_pretrained=load)))
        monkeypatch.setitem(sys.modules, "torchaudio", SimpleNamespace(save=lambda *args: None))
    else:
        def generate(*, text, reference_wav_path, cfg_value):
            assert reference_wav_path is None
            return [0.0]
        model = SimpleNamespace(tts_model=SimpleNamespace(sample_rate=48000), generate=generate)
        monkeypatch.setitem(sys.modules, "voxcpm", SimpleNamespace(
            VoxCPM=SimpleNamespace(from_pretrained=lambda *args, **kwargs: model)))
        monkeypatch.setitem(sys.modules, "soundfile", SimpleNamespace(write=lambda *args: None))
    assert module.main() == 0


def test_voxcpm_adapter_does_not_forward_chatterbox_controls(tmp_path):
    from backend.app.engines.base import EngineRequest
    from backend.app.engines.tts import VoxCPMEngine

    request = EngineRequest(kind="tts", output_dir=tmp_path,
                            params={"text": "Bonjour.", "temperature": 0.7, "exaggeration": 0.6})
    command = VoxCPMEngine()._cmd(request, tmp_path / "voice.wav")
    assert "--temperature" not in command
    assert "--exaggeration" not in command


def test_chatterbox_reuses_local_v3_weights_and_supplied_voice(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'scripts/gpu/tts_chatterbox.py'
    spec = importlib.util.spec_from_file_location('tts_cached_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reference = tmp_path / 'reference.wav'
    reference.write_bytes(b'reference')
    calls = {}

    def generate(text, **kwargs):
        calls.update(text=text, **kwargs)
        return [0.0]

    def local(path, *, device, t3_model):
        calls.update(model_dir=path, model=t3_model, device=device)
        return SimpleNamespace(sr=24000, generate=generate)

    monkeypatch.setattr(sys, 'argv', [str(script), '--model-dir', str(tmp_path), '--speaker-wav', str(reference),
                                     '--text', 'Bonjour.', '--out', str(tmp_path / 'voice.wav')])
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    monkeypatch.setitem(sys.modules, 'chatterbox.mtl_tts', SimpleNamespace(
        ChatterboxMultilingualTTS=SimpleNamespace(from_local=local)))
    monkeypatch.setitem(sys.modules, 'torchaudio', SimpleNamespace(save=lambda *args: None))
    assert module.main() == 0
    assert calls['model_dir'] == str(tmp_path)
    assert calls['model'] == 'v3'
    assert calls['audio_prompt_path'] == str(reference)
    assert calls['text'] == 'Bonjour.'


def test_avatar_mux_preserves_source_audio_and_uses_voice_duration(tmp_path):
    from app import media
    from app.avatar import finish_avatar, plan_audio
    from test_voice_first import wav_file
    import av
    import numpy as np
    raw, final = tmp_path / 'raw.mp4', tmp_path / 'final.mp4'
    audio = wav_file(tmp_path / 'source.wav', .8)
    media.run_ffmpeg(['-f', 'lavfi', '-i', 'color=c=blue:s=320x240:r=25:d=1.5', '-an', str(raw)])
    finish_avatar(raw, audio, final, plan_audio(.8))
    info = media.probe(final)
    assert info.has_audio and info.width == 720 and info.height == 1280
    assert info.duration_s == pytest.approx(.8, abs=.04)
    with av.open(str(final)) as container:
        decoded = np.concatenate([frame.to_ndarray().flatten() for frame in container.decode(audio=0)])
    assert np.sqrt(np.mean(decoded ** 2)) > .05
