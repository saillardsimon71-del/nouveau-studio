import base64
import wave

import pytest

from app.engines.base import EngineRequest


def test_longcat_rejects_audio_longer_than_one_segment_before_modal(tmp_path):
    from app.engines.modal_remote import ModalEngine

    wav = tmp_path / "long.wav"
    with wave.open(str(wav), "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x01\x00" * 64000)
    request = EngineRequest(kind="avatar", output_dir=tmp_path, inputs={"audio_path": str(wav)})
    with pytest.raises(ValueError, match="3.72"):
        ModalEngine("avatar").payload(request)


def test_longcat_result_without_audio_is_rejected(tmp_path):
    from app import media
    from app.engines.modal_remote import ModalEngine

    video = tmp_path / "silent.mp4"
    media.run_ffmpeg(["-f", "lavfi", "-i", "color=c=blue:s=180x320:r=25:d=0.5", "-an", str(video)])
    result = {"video_b64": base64.b64encode(video.read_bytes()).decode(), "metadata": {"gpu_wall_seconds": 10}}
    with pytest.raises(ValueError, match="audio"):
        ModalEngine("avatar").save_result(EngineRequest(kind="avatar", output_dir=tmp_path / "out"), result)


def test_modal_engines_disabled_without_opt_in(monkeypatch):
    from app.engines.modal_remote import ModalEngine

    monkeypatch.delenv("PVS_MODAL_ENABLED", raising=False)
    assert ModalEngine("video").available()[0] is False


def test_simulation_opt_out_also_blocks_explicit_engine_selection(monkeypatch):
    from app.config import get_settings
    from app.engines import registry
    from app.engines.base import EngineUnavailable

    monkeypatch.setattr(get_settings(), "allow_mock", False)
    with pytest.raises(EngineUnavailable):
        registry.resolve("avatar", "mock_avatar")
    assert not any(e["available"] for e in registry.catalog() if e["simulated"])


def test_poll_timeout_keeps_render_running(tmp_path, monkeypatch):
    from app import media
    from app.engines.modal_remote import ModalEngine

    video = tmp_path / "clip.mp4"
    media.run_ffmpeg(["-f", "lavfi", "-i", "color=c=blue:s=180x320:r=25:d=0.5", "-an", str(video)])
    result = {"video_base64": base64.b64encode(video.read_bytes()).decode(), "metadata": {"generation_seconds": 10}}

    class Call:
        polls = 0
        object_id = "fc-test"

        def get(self, timeout):
            self.polls += 1
            if self.polls == 1:
                raise TimeoutError()
            return result

        def cancel(self, **kwargs):
            raise AssertionError("A poll timeout must not cancel the render")

    class Function:
        def spawn(self, *args):
            return Call()

    class Context:
        def check_cancelled(self):
            pass

        def log(self, *args, **kwargs):
            pass

    engine = ModalEngine("video")
    monkeypatch.setattr(engine, "function", lambda: Function())
    request = EngineRequest(kind="video", output_dir=tmp_path / "out", params={"prompt": "test", "duration_s": 1})
    output = engine.run(request, Context())
    assert media.probe(output.artifacts[0]["path"]).width == 180
