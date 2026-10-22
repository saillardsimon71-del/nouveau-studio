"""CPU-only LongCat staging. Importing this app never constructs a CUDA image."""
import json
import os
from pathlib import Path

import modal

VOLUME_NAME = "pvs-longcat-models"
ROOT = Path("/models")
BASE = ROOT / "LongCat-Video"
AVATAR = ROOT / "LongCat-Video-Avatar-1.5"
app = modal.App("pvs-longcat-models")
models = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
download_image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "huggingface_hub>=0.26,<2", "hf_xet"
)
COMPONENTS = {
    "LongCat-Video": ("tokenizer", "text_encoder", "vae"),
    "LongCat-Video-Avatar-1.5": (
        "base_model_int8", "lora", "scheduler", "whisper-large-v3", "vocal_separator"
    ),
}


def inspection():
    manifest_path = ROOT / "pvs-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    invalid = []
    for name, size in manifest["files"].items():
        path = ROOT / name
        if not path.is_file() or path.stat().st_size != size or size <= 0:
            invalid.append(name)
    sections = {}
    for repo, folders in COMPONENTS.items():
        for folder in folders:
            prefix = f"{repo}/{folder}/"
            files = {n: s for n, s in manifest["files"].items() if n.startswith(prefix)}
            sections[prefix] = {
                "present": bool(files) and not any(n in invalid for n in files),
                "file_count": len(files), "bytes": sum(files.values()),
            }
    return {
        "volume": VOLUME_NAME, "sections": sections, "invalid_files": invalid,
        "bytes": sum(manifest["files"].values()),
        "revisions": manifest.get("revisions", {}),
        "ready": all(s["present"] for s in sections.values()),
    }


@app.function(image=download_image, cpu=4, memory=16384, timeout=7200, volumes={str(ROOT): models}, max_containers=1)
def prepare_models():
    from huggingface_hub import HfApi, snapshot_download

    os.environ.setdefault("HF_HOME", str(ROOT / ".hf_cache"))
    manifest = {"files": {}, "revisions": {}}
    for repo, folders in COMPONENTS.items():
        repo_id = f"meituan-longcat/{repo}"
        info = HfApi().model_info(repo_id, files_metadata=True)
        manifest["revisions"][repo_id] = info.sha
        for sibling in info.siblings:
            if sibling.rfilename.split("/")[0] in folders:
                manifest["files"][f"{repo}/{sibling.rfilename}"] = sibling.size
        print(f"Checking/downloading {repo_id} at {info.sha}", flush=True)
        snapshot_download(
            repo_id=repo_id, revision=info.sha, local_dir=str(ROOT / repo),
            allow_patterns=[f"{folder}/**" for folder in folders], max_workers=5,
        )
        models.commit()
    (ROOT / "pvs-manifest.json").write_text(json.dumps(manifest, indent=2))
    models.commit()
    report = inspection()
    if not report["ready"]:
        raise RuntimeError(f"Incomplete model volume: {json.dumps(report)}")
    return report


@app.function(image=download_image, cpu=1, memory=2048, timeout=600, volumes={str(ROOT): models})
def doctor():
    return inspection()


@app.local_entrypoint()
def main(mode: str = "doctor", json_out: str = "artifacts/longcat_models.json"):
    if mode not in ("prepare", "doctor"):
        raise SystemExit("Allowed modes: prepare, doctor")
    report = prepare_models.remote() if mode == "prepare" else doctor.remote()
    path = Path(json_out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["ready"]:
        raise SystemExit("Models not ready: use --mode prepare")
