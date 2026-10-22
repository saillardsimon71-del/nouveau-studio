"""Contract tests for the Modal LTX worker, without Modal and without a GPU.

The worker module is imported against a stub `modal` package so that the request
validation and the ComfyUI graph can be checked in CI on a laptop. Nothing here
proves a render works — that needs the real GPU run.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER = REPO_ROOT / "deploy" / "modal_ltx_worker.py"


class _Stub:
    """Anything the worker chains on at import time."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return _Stub(*args, **kwargs)

    def __getattr__(self, name):
        return _Stub()

    def __iter__(self):
        return iter(())


def _install_stub_modal(monkeypatch):
    module = types.ModuleType("modal")
    module.App = lambda *a, **k: _Stub(*a, **k)
    module.Image = types.SimpleNamespace(debian_slim=lambda *a, **k: _Stub())
    module.Volume = types.SimpleNamespace(from_name=lambda *a, **k: _Stub())
    module.enter = _Stub()
    monkeypatch.setitem(sys.modules, "modal", module)


@pytest.fixture()
def worker(monkeypatch):
    _install_stub_modal(monkeypatch)
    spec = importlib.util.spec_from_file_location("pvs_worker_under_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GOOD = {"prompt": "une rue mouillée à l'aube, caméra latérale lente", "duration_s": 5, "aspect_ratio": "9:16"}


def test_defaults_resolve_to_vertical_768x1344(worker):
    request = worker.validate(dict(GOOD))
    assert (request["width"], request["height"]) == (768, 1344)
    assert request["fps"] == 24
    assert request["steps"] == 8
    assert request["trace_id"].startswith("pvs-")
    assert request["audio_mode"] == "native"


@pytest.mark.parametrize("seconds", [1, 3, 5, 7.5, 15])
def test_frame_count_is_on_the_8k_plus_1_grid(worker, seconds):
    request = worker.validate({**GOOD, "duration_s": seconds})
    assert (request["frames"] - 1) % 8 == 0
    assert 25 <= request["frames"] <= 361
    assert abs(request["duration_s"] - request["frames"] / 24) < 0.002


def test_frame_count_is_clamped_not_rejected(worker):
    assert worker.validate({**GOOD, "duration_s": 1})["frames"] == 25
    assert worker.validate({**GOOD, "duration_s": 15})["frames"] == 361


@pytest.mark.parametrize(
    "patch, message",
    [
        ({"prompt": "   "}, "prompt"),
        ({"duration_s": 0.5}, "duration_s"),
        ({"duration_s": 16}, "duration_s"),
        ({"aspect_ratio": "4:3"}, "aspect_ratio"),
        ({"audio_mode": "music"}, "audio_mode"),
        ({"seed": -1}, "seed"),
        ({"seed": "42"}, "seed"),
        ({"seed": True}, "seed"),
        ({"image_png_base64": "bm90IGEgcG5n"}, "PNG"),
        ({"image_png_base64": "!!!notbase64!!!"}, "base64"),
        ({"image_strength": 1.5}, "image_strength"),
        ({"trace_id": "bad id/with slash"}, "trace_id"),
    ],
)
def test_invalid_requests_are_rejected(worker, patch, message):
    with pytest.raises(ValueError) as error:
        worker.validate({**GOOD, **patch})
    assert message in str(error.value)


def test_png_reference_is_accepted(worker):
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
    request = worker.validate({**GOOD, "image_png_base64": png, "image_strength": 0.55})
    assert request["image_strength"] == 0.55
    assert request["image_png_base64"] == png


def test_two_pass_graph_uses_pinned_weights_and_upsampler(worker):
    request = worker.validate(dict(GOOD))
    graph = worker.build_graph(request, output_prefix="pvs/test")
    assert graph["6"]["inputs"]["unet_name"] == worker.LTX_MODEL_FILES["unet"]
    assert graph["13"]["inputs"]["clip_name"] == worker.LTX_MODEL_FILES["clip"]
    assert graph["91"]["inputs"]["fps"] == 24
    assert graph["30"]["inputs"]["length"] == request["frames"]
    # first pass at half resolution, second pass through the x2 upsampler
    assert graph["30"]["inputs"]["width"] == request["width"] // 2
    assert graph["36"]["class_type"] == "LTXVLatentUpsampler"
    assert graph["41"]["class_type"] == "SamplerCustomAdvanced"
    assert graph["92"]["inputs"]["filename_prefix"] == "pvs/test"
    # native audio is wired into the video
    assert graph["23"]["class_type"] == "LTXVAudioVAEDecode"
    assert graph["91"]["inputs"]["audio"] == ["23", 0]


def test_silent_mode_drops_the_audio_decode(worker):
    graph = worker.build_graph(worker.validate({**GOOD, "audio_mode": "silent"}), output_prefix="pvs/silent")
    assert "23" not in graph
    assert "audio" not in graph["91"]["inputs"]


def test_reference_image_switches_continuity_to_image(worker):
    request = worker.validate(dict(GOOD))
    graph = worker.build_graph(request, output_prefix="pvs/img", uploaded_image="ref.png")
    assert graph["1"]["inputs"]["image"] == "ref.png"
    assert graph["31"]["class_type"] == "LTXVImgToVideoInplace"
    assert graph["33"]["inputs"]["video_latent"] == ["31", 0]
    assert graph["37"]["inputs"]["strength"] == 1.0
    assert graph["38"]["inputs"]["video_latent"] == ["37", 0]


def test_graph_prefix_cannot_escape_the_output_folder(worker):
    request = worker.validate(dict(GOOD))
    with pytest.raises(ValueError):
        worker.build_graph(request, output_prefix="/absolute")
    with pytest.raises(ValueError):
        worker.build_graph(request, output_prefix="a/../../etc")


def test_render_entrypoint_writes_the_mp4_and_metadata(worker, monkeypatch, tmp_path):
    """The exact code path GitHub Actions runs, against a fake remote function."""
    payload = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 256
    seen = {}

    class FakeRender:
        @staticmethod
        def remote(request):
            seen.update(request)
            return {
                "video_base64": base64.b64encode(payload).decode(),
                "metadata": {
                    "bytes": len(payload),
                    "duration_sec": 5.0,
                    "width": 768,
                    "height": 1344,
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "has_audio": True,
                    "generation_seconds": 100.0,
                },
            }

    monkeypatch.setattr(worker, "render_clip", FakeRender)
    out = tmp_path / "artifacts" / "clip.mp4"
    worker.main(mode="render", prompt="test", duration=5, out=str(out))

    assert out.read_bytes() == payload
    metadata = json.loads((tmp_path / "artifacts" / "clip.json").read_text())
    assert metadata["cost_estimate_usd"] > 0
    assert "estimation" in metadata["cost_note"]
    assert seen["aspect_ratio"] == "9:16"
    assert seen["duration_s"] == 5


def test_render_entrypoint_requires_a_prompt(worker, tmp_path):
    with pytest.raises(SystemExit):
        worker.main(mode="render", prompt="   ", out=str(tmp_path / "x.mp4"))


def test_render_entrypoint_rejects_a_non_png_reference(worker, tmp_path):
    bad = tmp_path / "ref.png"
    bad.write_bytes(b"GIF89a not a png")
    with pytest.raises(SystemExit):
        worker.main(mode="render", prompt="x", image_png=str(bad), out=str(tmp_path / "x.mp4"))


def test_unknown_mode_fails_loudly(worker):
    with pytest.raises(SystemExit):
        worker.main(mode="benchmark")


def test_doctor_entrypoint_fails_when_weights_are_missing(worker, monkeypatch, tmp_path):
    class FakeDoctor:
        @staticmethod
        def remote():
            return {
                "app": "pvs-ltx",
                "volume_name": "studio-ltx25-models",
                "weights_present": 1,
                "weights_expected": 5,
                "ready_for_ltx": False,
                "weights": {"unet": {"present": True}, "clip": {"present": False}},
            }

    monkeypatch.setattr(worker, "doctor", FakeDoctor)
    with pytest.raises(SystemExit) as error:
        worker.main(mode="doctor", json_out=str(tmp_path / "doctor.json"))
    assert "clip" in str(error.value)
    assert json.loads((tmp_path / "doctor.json").read_text())["ready_for_ltx"] is False


def test_cost_estimate_uses_published_rates(worker):
    # 100 s on L40S: GPU 0.0542 + CPU 0.0105 + RAM 0.0142 -> ~0.079 $
    estimate = worker.estimate_cost_usd("L40S", 100)
    assert 0.07 <= estimate <= 0.09
    assert worker.estimate_cost_usd("unknown-gpu", 100) < 0.03


def test_video_source_is_encoded_before_partial_denoising(worker):
    request = worker.validate({**GOOD, "video_mp4_base64": base64.b64encode(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64).decode()})
    assert request["steps"] == 3
    graph = worker.build_graph(request, output_prefix="pvs/v2v", uploaded_video="motion.mp4")
    latent = graph[graph["33"]["inputs"]["video_latent"][0]]
    assert latent["class_type"] == "VAEEncodeTiled"
    resize = graph[latent["inputs"]["pixels"][0]]
    components = graph[resize["inputs"]["image"][0]]
    video = graph[components["inputs"]["video"][0]]
    assert video == {"class_type": "LoadVideo", "inputs": {"file": "motion.mp4"}}
    assert components["class_type"] == "GetVideoComponents"
    assert resize["inputs"]["width"] == request["width"] // 2
    assert 0 < float(graph["9"]["inputs"]["sigmas"].split(",")[0]) < 1


@pytest.mark.parametrize("value", ["bad!", base64.b64encode(b"not mp4").decode()])
def test_invalid_video_source_rejected_before_gpu(worker, value):
    with pytest.raises(ValueError, match="video_mp4_base64"):
        worker.validate({**GOOD, "video_mp4_base64": value})


def test_wait_for_video_polls_comfyui_history(worker, monkeypatch, tmp_path):
    """The polling loop, against a fake ComfyUI: it must return the written MP4."""
    import http.server
    import threading
    import time

    output = tmp_path / "output" / "pvs"
    output.mkdir(parents=True)
    # exactly what ComfyUI's SaveVideo produces for prefix "pvs/trace-1"
    video = output / "trace-1_00001_.mp4"
    video.write_bytes(b"\x00" * 4096)

    calls = {"history": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.startswith("/history/"):
                calls["history"] += 1
                if calls["history"] < 2:
                    body = {"trace": {"status": {}}}
                else:
                    body = {
                        "trace": {
                            "status": {"status_str": "success", "completed": True},
                            "outputs": {
                                "92": {
                                    "videos": [
                                        {"filename": "trace-1_00001_.mp4", "subfolder": "pvs", "type": "output"}
                                    ]
                                }
                            },
                        }
                    }
            else:
                body = {}
            payload = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(worker, "COMFY_API", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(worker, "COMFYUI_DIR", tmp_path)
    started = time.time()
    try:
        found = worker._wait_for_video("trace", "pvs/trace-1")
    finally:
        server.shutdown()
    assert found == video
    assert calls["history"] >= 2
    assert time.time() - started < 20


def test_wait_for_video_raises_on_comfyui_error(worker, monkeypatch, tmp_path):
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            payload = json.dumps(
                {"x": {"status": {"status_str": "error", "messages": ["VRAM out of memory"]}}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(worker, "COMFY_API", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(worker, "COMFYUI_DIR", tmp_path)
    try:
        with pytest.raises(RuntimeError) as error:
            worker._wait_for_video("x", "pvs/x")
    finally:
        server.shutdown()
    assert "VRAM out of memory" in str(error.value)
