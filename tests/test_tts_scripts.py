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
