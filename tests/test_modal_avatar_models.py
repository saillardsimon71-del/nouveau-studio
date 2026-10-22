import importlib
import json


def test_cpu_entrypoint_never_defines_a_cuda_image(monkeypatch):
    import modal

    def forbidden(*args, **kwargs):
        raise AssertionError("CPU staging must not define a CUDA image")

    monkeypatch.setattr(modal.Image, "from_registry", forbidden)
    module = importlib.import_module("deploy.modal_avatar_models")
    assert module.prepare_models is not None
    assert module.doctor is not None


def test_doctor_rejects_truncated_checkpoint(tmp_path, monkeypatch):
    module = importlib.import_module("deploy.modal_avatar_models")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    checkpoint = tmp_path / "LongCat-Video-Avatar-1.5" / "base_model_int8" / "weights.safetensors"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"partial")
    manifest = {"files": {"LongCat-Video-Avatar-1.5/base_model_int8/weights.safetensors": 100}}
    (tmp_path / "pvs-manifest.json").write_text(json.dumps(manifest))
    report = module.inspection()
    assert not report["ready"]
    assert report["invalid_files"] == ["LongCat-Video-Avatar-1.5/base_model_int8/weights.safetensors"]
