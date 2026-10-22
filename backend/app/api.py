"""HTTP API. Thin: validation, persistence, job enqueue, file serving."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from . import cost, db, jobs, media, qc
from .config import get_settings
from .director import propose
from .engines import registry
from .schemas import (
    CharacterCreate,
    ExportRequest,
    GenerateRequest,
    ProjectCreate,
    ProjectUpdate,
    RetakeRequest,
    ShotCreate,
    ShotPatch,
    Storyboard,
    StoryboardRequest,
    VoiceCreate,
)

router = APIRouter(prefix="/api")
ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_AUDIO = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
ALLOWED_VIDEO = {".mp4", ".mov", ".webm", ".mkv"}
DEFAULT_VIDEO_MIME = {"video": "video/mp4", "image": "image/png", "audio": "audio/wav"}


# ---------------------------------------------------------------------------- system
@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "db": str(get_settings().db_path)}


@router.get("/system")
def system() -> dict[str, Any]:
    s = get_settings()
    return {
        "ffmpeg": media.ffmpeg_version(),
        "ffmpeg_path": s.ffmpeg,
        "data_dir": str(s.data_dir),
        "engines": registry.catalog(),
        "director": {
            "llm_configured": bool(s.llm_api_key),
            "base_url": s.llm_base_url,
            "model": s.llm_model,
            "fallback": "heuristic",
        },
        "provider": s.default_provider,
        "rate_card": s.rate_card,
        "workers": s.max_workers,
        "job_stats": jobs.stats(),
        "blockers": _blockers(),
    }


def _blockers() -> list[str]:
    """Things that stop real generation here, stated plainly instead of guessed."""
    blockers = []
    catalog = registry.catalog()
    if not any(e["kind"] == "video" and not e["simulated"] and e["available"] for e in catalog):
        blockers.append("Aucun moteur vidéo réel disponible (GPU + poids LTX-2.5 requis).")
    if not any(e["kind"] == "avatar" and not e["simulated"] and e["available"] for e in catalog):
        blockers.append("Aucun moteur avatar réel disponible (GPU + poids LongCat-Video-Avatar 1.5 requis).")
    if not any(e["kind"] == "tts" and not e["simulated"] and e["available"] for e in catalog):
        blockers.append("Aucun moteur de voix réel disponible (Chatterbox/VoxCPM2 non installés).")
    if not get_settings().llm_api_key:
        blockers.append("Aucune clé LLM configurée : le directeur utilise son template local.")
    return blockers


# ---------------------------------------------------------------------------- projects
@router.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    projects = db.find("projects", "", order="updated_at DESC")
    for project in projects:
        shots = db.find("shots", "project_id = ?", (project["id"],), order="idx ASC")
        project["shot_count"] = len(shots)
        project["generated_count"] = sum(1 for s in shots if s.get("selected_artifact"))
        project["total_duration_s"] = round(sum(s.get("duration_s") or 0 for s in shots), 2)
    return projects


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate) -> dict[str, Any]:
    now = db.now_iso()
    return db.insert(
        "projects",
        {
            "id": db.new_id("proj"),
            "name": body.name,
            "brief": body.brief,
            "format": body.format,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        },
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    project = _require("projects", project_id)
    shot_rows = db.find("shots", "project_id = ?", (project_id,), order="idx ASC")
    for shot in shot_rows:
        shot["artifacts"] = db.find("artifacts", "shot_id = ?", (shot["id"],), order="created_at DESC")
        shot["character"] = db.get("characters", shot["character_id"]) if shot.get("character_id") else None
        shot["voice"] = db.get("voices", shot["voice_id"]) if shot.get("voice_id") else None
    spent = 0.0
    cursor = 0.0
    for shot in shot_rows:
        shot["start_s"] = round(cursor, 2)
        cursor += float(shot.get("duration_s") or 0)
    project["shots"] = shot_rows
    project["exports"] = db.find("exports", "project_id = ?", (project_id,), order="created_at DESC")
    project["cost"] = cost.project_summary(project_id)
    project["total_duration_s"] = round(cursor, 2)
    return project


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdate) -> dict[str, Any]:
    _require("projects", project_id)
    patch = body.model_dump(exclude_none=True)
    patch["updated_at"] = db.now_iso()
    return db.update("projects", project_id, patch) or {}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, bool]:
    _require("projects", project_id)
    for shot in db.find("shots", "project_id = ?", (project_id,)):
        db.delete("shots", shot["id"])
    return {"deleted": db.delete("projects", project_id)}


# ---------------------------------------------------------------------------- director
@router.post("/director/propose")
def director_propose(body: StoryboardRequest) -> dict[str, Any]:
    character = db.get("characters", body.character_id) if body.character_id else None
    result = propose(
        brief=body.brief,
        target_duration_s=body.target_duration_s,
        character=character,
        extra=body.extra_instructions,
        use_llm=body.use_llm,
    )
    return {
        "source": result.source,
        "model": result.model,
        "notes": result.notes,
        "storyboard": result.storyboard.model_dump(),
    }


@router.post("/projects/{project_id}/storyboard")
def apply_storyboard(project_id: str, body: Storyboard, replace: bool = Query(default=True)) -> dict[str, Any]:
    project = _require("projects", project_id)
    if replace:
        for shot in db.find("shots", "project_id = ?", (project_id,)):
            db.delete("shots", shot["id"])
    now = db.now_iso()
    start_idx = len(db.find("shots", "project_id = ?", (project_id,))) if not replace else 0
    characters = db.find("characters", "project_id = ? OR project_id IS NULL", (project_id,), order="created_at ASC")
    default_character = characters[0]["id"] if characters else None
    for offset, spec in enumerate(body.shots):
        db.insert(
            "shots",
            {
                "id": db.new_id("shot"),
                "project_id": project_id,
                "idx": start_idx + offset,
                "kind": spec.kind,
                "title": spec.title,
                "duration_s": spec.duration_s,
                "dialogue": spec.dialogue,
                "prompt": spec.prompt,
                "camera": spec.camera,
                "character_id": default_character if spec.kind == "avatar" else None,
                "transition": spec.transition,
                "status": "draft",
                "params": {"engine_hint": spec.engine_hint, "notes": spec.notes},
                "created_at": now,
                "updated_at": now,
            },
        )
    db.update(
        "projects",
        project_id,
        {
            "concept": body.concept or project.get("concept", ""),
            "script": body.script or project.get("script", ""),
            "style_guide": body.style_guide or project.get("style_guide", ""),
            "status": "storyboarded",
            "updated_at": now,
        },
    )
    return get_project(project_id)


# ---------------------------------------------------------------------------- shots
@router.post("/projects/{project_id}/shots", status_code=201)
def add_shot(project_id: str, body: ShotCreate) -> dict[str, Any]:
    _require("projects", project_id)
    existing = db.find("shots", "project_id = ?", (project_id,), order="idx ASC")
    now = db.now_iso()
    return db.insert(
        "shots",
        {
            "id": db.new_id("shot"),
            "project_id": project_id,
            "idx": len(existing),
            "kind": body.kind,
            "title": body.title,
            "duration_s": body.duration_s,
            "dialogue": body.dialogue,
            "prompt": body.prompt,
            "camera": body.camera,
            "character_id": body.character_id,
            "transition": body.transition,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        },
    )


@router.patch("/shots/{shot_id}")
def patch_shot(shot_id: str, body: ShotPatch) -> dict[str, Any]:
    _require("shots", shot_id)
    patch = body.model_dump(exclude_none=True)
    patch["updated_at"] = db.now_iso()
    return db.update("shots", shot_id, patch) or {}


@router.delete("/shots/{shot_id}")
def delete_shot(shot_id: str) -> dict[str, bool]:
    _require("shots", shot_id)
    return {"deleted": db.delete("shots", shot_id)}


@router.post("/shots/{shot_id}/generate", status_code=202)
def generate_shot(shot_id: str, body: GenerateRequest | None = None) -> dict[str, Any]:
    shot = _require("shots", shot_id)
    body = body or GenerateRequest()
    job_type = "avatar" if shot["kind"] == "avatar" else "video"
    if shot["kind"] in ("title",):
        job_type = "video"
    params: dict[str, Any] = dict(body.params)
    hint = (shot.get("params") or {}).get("engine_hint") or ""
    # an engine_hint may name a *kind* ("avatar", "screen_capture") rather than an
    # engine; only honour it when it resolves to an actual adapter
    requested = body.engine or (hint if hint in registry.names() else None)
    params["engine"] = requested
    if job_type == "avatar" and not shot.get("dialogue"):
        raise HTTPException(400, "plan avatar sans dialogue : écrire le texte avant de générer")
    return jobs.enqueue(project_id=shot["project_id"], shot_id=shot_id, job_type=job_type,
                        engine=body.engine, params=params)


@router.post("/shots/{shot_id}/voice", status_code=202)
def generate_voice(shot_id: str, body: GenerateRequest | None = None) -> dict[str, Any]:
    shot = _require("shots", shot_id)
    if not (shot.get("dialogue") or "").strip():
        raise HTTPException(400, "aucun dialogue à synthétiser")
    body = body or GenerateRequest()
    return jobs.enqueue(project_id=shot["project_id"], shot_id=shot_id, job_type="tts",
                        engine=body.engine, params=dict(body.params))


@router.post("/shots/{shot_id}/retake", status_code=202)
def retake_shot(shot_id: str, body: RetakeRequest) -> dict[str, Any]:
    shot = _require("shots", shot_id)
    return jobs.enqueue(
        project_id=shot["project_id"], shot_id=shot_id, job_type="retake",
        engine="ltx_native", params=body.model_dump(),
    )


@router.post("/shots/{shot_id}/select/{artifact_id}")
def select_artifact(shot_id: str, artifact_id: str) -> dict[str, Any]:
    _require("shots", shot_id)
    artifact = _require("artifacts", artifact_id)
    db.update("shots", shot_id, {"selected_artifact": artifact_id, "status": "generated", "updated_at": db.now_iso()})
    return {"selected": artifact_id, "kind": artifact["kind"]}


@router.post("/shots/{shot_id}/upload")
async def upload_shot_media(shot_id: str, file: UploadFile = File(...), kind: str = Query(default="video")) -> dict[str, Any]:
    shot = _require("shots", shot_id)
    stored = await _save_upload(file, ALLOWED_VIDEO | ALLOWED_IMAGE | ALLOWED_AUDIO)
    artifact_kind = kind if kind in {"video", "image", "audio"} else "video"
    if DEFAULT_VIDEO_MIME.get(artifact_kind) is None:
        raise HTTPException(400, f"type d'artefact non supporté: {artifact_kind}")
    artifact = _store_artifact(
        stored, artifact_kind, file.content_type or DEFAULT_VIDEO_MIME[artifact_kind],
        project_id=shot["project_id"], shot_id=shot_id,
        meta={"source": "upload", "filename": file.filename},
    )
    if artifact_kind == "video":
        inspection = qc.inspect_clip(stored, expected_duration_s=shot.get("duration_s"))
        db.update("shots", shot_id, {"selected_artifact": artifact["id"], "status": "generated",
                                     "qc": inspection, "updated_at": db.now_iso()})
        artifact["qc"] = inspection
    return artifact


# ---------------------------------------------------------------------------- characters & voices
@router.get("/characters")
def list_characters() -> list[dict[str, Any]]:
    return db.find("characters", "", order="updated_at DESC")


@router.post("/characters", status_code=201)
def create_character(body: CharacterCreate) -> dict[str, Any]:
    now = db.now_iso()
    return db.insert(
        "characters",
        {
            "id": db.new_id("char"),
            "name": body.name,
            "description": body.description,
            "appearance": body.appearance,
            "base_image": body.base_image,
            "voice_id": body.voice_id,
            "refs": body.refs,
            "project_id": body.project_id,
            "created_at": now,
            "updated_at": now,
        },
    )


@router.patch("/characters/{character_id}")
def update_character(character_id: str, body: dict[str, Any]) -> dict[str, Any]:
    _require("characters", character_id)
    allowed = {"name", "description", "appearance", "base_image", "voice_id", "refs"}
    patch = {k: v for k, v in body.items() if k in allowed}
    patch["updated_at"] = db.now_iso()
    return db.update("characters", character_id, patch) or {}


@router.delete("/characters/{character_id}")
def delete_character(character_id: str) -> dict[str, bool]:
    _require("characters", character_id)
    return {"deleted": db.delete("characters", character_id)}


@router.post("/characters/{character_id}/image")
async def upload_character_image(character_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    character = _require("characters", character_id)
    stored = await _save_upload(file, ALLOWED_IMAGE)
    artifact = _store_artifact(
        stored, "image", file.content_type or "image/jpeg",
        project_id=character.get("project_id"),
        meta={"source": "upload", "role": "character_reference", "filename": file.filename},
    )
    appearance = dict(character.get("appearance") or {})
    try:
        info = media.probe(stored)
        if info.width:
            appearance["reference_size"] = f"{info.width}x{info.height}"
    except media.MediaError:
        appearance["reference_size"] = "unknown"
    return db.update(
        "characters",
        character_id,
        {"base_image": artifact["id"], "appearance": appearance, "updated_at": db.now_iso()},
    ) or {}


@router.get("/voices")
def list_voices() -> list[dict[str, Any]]:
    return db.find("voices", "", order="created_at DESC")


@router.post("/voices", status_code=201)
def create_voice(body: VoiceCreate) -> dict[str, Any]:
    return db.insert(
        "voices",
        {
            "id": db.new_id("voice"),
            "name": body.name,
            "engine": body.engine,
            "language": body.language,
            "ref_audio": body.ref_audio,
            "transcript": body.transcript,
            "params": body.params,
            "created_at": db.now_iso(),
        },
    )


@router.post("/voices/{voice_id}/sample")
async def upload_voice_sample(voice_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    voice = _require("voices", voice_id)
    stored = await _save_upload(file, ALLOWED_AUDIO)
    artifact = _store_artifact(
        stored, "audio", file.content_type or "audio/wav",
        meta={"source": "upload", "role": "voice_reference", "filename": file.filename},
    )
    params = dict(voice.get("params") or {})
    try:
        params["sample_seconds"] = media.probe(stored).duration_s
    except media.MediaError:
        params["sample_seconds"] = None
    return db.update("voices", voice_id, {"ref_audio": artifact["id"], "params": params}) or {}


# ---------------------------------------------------------------------------- jobs & exports
@router.get("/jobs")
def list_jobs(project_id: str | None = None, limit: int = Query(default=50, le=200)) -> list[dict[str, Any]]:
    where = "project_id = ?" if project_id else ""
    args = (project_id,) if project_id else ()
    return db.find("jobs", where, args, order="created_at DESC", limit=limit)


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = _require("jobs", job_id)
    job["artifacts"] = db.find("artifacts", "job_id = ?", (job_id,))
    job["log"] = jobs.job_log_tail(job_id, lines=40)
    return job


@router.get("/jobs/{job_id}/log", response_class=PlainTextResponse)
def get_job_log(job_id: str) -> str:
    _require("jobs", job_id)
    return jobs.job_log_tail(job_id, lines=400)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    job = _require("jobs", job_id)
    if job["status"] in {"queued", "running"}:
        db.update("jobs", job_id, {"status": "cancelled", "finished_at": db.now_iso(), "stage": "cancelled"})
    return db.get("jobs", job_id) or {}


@router.post("/jobs/{job_id}/retry", status_code=201)
def retry_job(job_id: str) -> dict[str, Any]:
    job = _require("jobs", job_id)
    return jobs.enqueue(project_id=job.get("project_id"), shot_id=job.get("shot_id"),
                        job_type=job["type"], engine=job.get("engine"), params=dict(job.get("params") or {}))


@router.post("/projects/{project_id}/export", status_code=202)
def export_project(project_id: str, body: ExportRequest | None = None) -> dict[str, Any]:
    _require("projects", project_id)
    body = body or ExportRequest()
    params = body.model_dump()
    params["music_path"] = params.get("music_path") or db.get("projects", project_id).get("music_path")
    return jobs.enqueue(project_id=project_id, shot_id=None, job_type="assembly",
                        engine="ffmpeg_assembly", params=params)


@router.get("/projects/{project_id}/exports")
def list_exports(project_id: str) -> list[dict[str, Any]]:
    _require("projects", project_id)
    return db.find("exports", "project_id = ?", (project_id,), order="created_at DESC")


@router.get("/exports/{export_id}")
def get_export(export_id: str) -> dict[str, Any]:
    return _require("exports", export_id)


@router.get("/exports/{export_id}/file")
def download_export(export_id: str) -> FileResponse:
    export = _require("exports", export_id)
    path = Path(export["path"])
    if not path.exists():
        raise HTTPException(410, "fichier d'export supprimé")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str) -> dict[str, Any]:
    return _require("artifacts", artifact_id)


@router.get("/artifacts/{artifact_id}/file")
def download_artifact(artifact_id: str) -> FileResponse:
    artifact = _require("artifacts", artifact_id)
    path = Path(artifact["path"])
    if not path.exists():
        raise HTTPException(410, "fichier supprimé")
    return FileResponse(path, media_type=artifact["mime"], filename=path.name)


@router.get("/projects/{project_id}/cost")
def project_cost(project_id: str) -> dict[str, Any]:
    _require("projects", project_id)
    return cost.project_summary(project_id)


# ---------------------------------------------------------------------------- helpers
def _store_artifact(
    path: Path,
    kind: str,
    mime: str,
    *,
    project_id: str | None = None,
    shot_id: str | None = None,
    job_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register an uploaded file as an artifact.

    The UI addresses media by artifact id (not by path), so every upload must
    produce a row; the id is what gets stored on characters/voices/shots.
    """
    return db.insert(
        "artifacts",
        {
            "id": db.new_id("art"),
            "job_id": job_id,
            "project_id": project_id,
            "shot_id": shot_id,
            "kind": kind,
            "path": str(path),
            "mime": mime,
            "bytes": path.stat().st_size,
            "meta": meta or {},
            "selected": 0,
            "created_at": db.now_iso(),
        },
    )


def _require(table: str, row_id: str) -> dict[str, Any]:
    row = db.get(table, row_id)
    if row is None:
        raise HTTPException(404, f"{table}: {row_id} introuvable")
    return row


async def _save_upload(file: UploadFile, allowed: set[str]) -> Path:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(415, f"extension non autorisée: {suffix or 'inconnue'}")
    settings = get_settings()
    target = settings.data_dir / "uploads" / f"{uuid.uuid4().hex}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    if target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "fichier vide")
    if target.stat().st_size > 800 * 1024 * 1024:
        target.unlink(missing_ok=True)
        raise HTTPException(413, "fichier trop volumineux (800 Mo max)")
    return target
