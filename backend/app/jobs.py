"""Job orchestration.

Deliberately small: a dispatcher thread pulls `queued` rows from SQLite and hands
them to a bounded thread pool. No broker, no Celery, no distributed queue — the
studio runs one process and one GPU at a time, and jobs survive a restart
because their state is in the database, not in memory.

What the runner owns:
  * job lifecycle and progress,
  * engine selection + explicit simulation fallback,
  * artifact registration and shot linkage,
  * cost accounting (including failed attempts),
  * QC after generation,
  * composition of the small multi-step pipelines (voice -> avatar, retake -> splice).
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import cost, db, media, qc
from .config import get_settings
from .engines import registry
from .engines.assembly import AssemblyEngine, splice_region
from .engines.base import EngineOutput, EngineRequest, EngineUnavailable

_running: set[str] = set()
_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_dispatcher: threading.Thread | None = None
_stop = threading.Event()


def log_path(job_id: str) -> Path:
    return get_settings().data_dir / "tmp" / f"{job_id}.log"


class Ctx:
    """What an engine is allowed to touch while it runs."""

    def __init__(self, job: dict[str, Any]) -> None:
        self.job_id = job["id"]
        self.logs: list[str] = []
        self._path = log_path(self.job_id)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("", encoding="utf-8")
        self._last_update = 0.0

    def log(self, message: str, progress: float | None = None, stage: str = "") -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        self.logs.append(line)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        payload: dict[str, Any] = {}
        if progress is not None:
            payload["progress"] = max(0.0, min(1.0, progress))
        if stage:
            payload["stage"] = stage
        now = time.time()
        if payload and (now - self._last_update > 1.0 or (progress or 0) >= 0.99):
            db.update("jobs", self.job_id, payload)
            self._last_update = now

    def check_cancelled(self) -> None:
        row = db.fetchone("SELECT status FROM jobs WHERE id = ?", (self.job_id,))
        if row is None or row["status"] == "cancelled":
            raise RuntimeError("job annulé")


# ----------------------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------------------
def enqueue(
    *,
    project_id: str | None,
    shot_id: str | None,
    job_type: str,
    engine: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    job = db.insert(
        "jobs",
        {
            "id": db.new_id("job"),
            "project_id": project_id,
            "shot_id": shot_id,
            "type": job_type,
            "engine": engine or "auto",
            "params": params or {},
            "status": "queued",
            "provider": settings.default_provider,
            "gpu": "CPU",
            "created_at": db.now_iso(),
        },
    )
    _wake()
    return job


def start() -> None:
    global _executor, _dispatcher
    settings = get_settings()
    if settings.requeue_on_boot:
        with db.tx() as conn:
            conn.execute("UPDATE jobs SET status = 'queued', stage = 'requeued after restart' WHERE status = 'running'")
    _executor = ThreadPoolExecutor(max_workers=max(1, settings.max_workers), thread_name_prefix="pvs-job")
    _dispatcher = threading.Thread(target=_dispatch_loop, name="pvs-dispatch", daemon=True)
    _dispatcher.start()


def shutdown() -> None:
    _stop.set()
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)


def _wake() -> None:
    """Dispatcher polls; wake it up early when a job is queued."""
    # simple: the loop sleeps 0.4s, so nothing else is needed. Kept for clarity.
    return


def _dispatch_loop() -> None:
    while not _stop.is_set():
        try:
            _dispatch_once()
        except Exception:  # pragma: no cover - dispatcher must never die
            traceback.print_exc()
        _stop.wait(0.4)


def _dispatch_once() -> None:
    global _running
    with _lock:
        capacity = max(1, get_settings().max_workers) - len(_running)
        if capacity <= 0:
            return
        rows = db.find("jobs", "status = 'queued'", order="created_at ASC", limit=capacity + len(_running) + 4)
        started = 0
        for row in rows:
            if started >= capacity:
                break
            if row["id"] in _running:
                continue
            _running.add(row["id"])
            started += 1
            assert _executor is not None
            _executor.submit(_run_job, row["id"])


# ----------------------------------------------------------------------------------------
# Execution
# ----------------------------------------------------------------------------------------
def _run_job(job_id: str) -> None:
    job = db.get("jobs", job_id)
    if job is None or job["status"] != "queued":
        with _lock:
            _running.discard(job_id)
        return
    ctx = Ctx(job)
    started_wall = time.time()
    db.update(
        "jobs",
        job_id,
        {"status": "running", "started_at": db.now_iso(), "attempts": (job.get("attempts") or 0) + 1, "stage": "start"},
    )
    try:
        output, requested_engine, fallback, simulated = _dispatch(job, ctx)
        usage = output.usage
        usage.notes = usage.notes or output.notes
        cost.record(job["project_id"], job_id, usage, note=f"{job['type']}/{requested_engine}")
        artifacts = _register_artifacts(job, output)
        primary = _primary_artifact(artifacts)
        # Link the results *before* flipping the job to succeeded: the UI polls
        # the job status, and a succeeded job must already have visible effects.
        _link_shot(job, primary, output, simulated)
        if job["type"] == "assembly":
            _link_export_assets(job, artifacts)
        db.update(
            "jobs",
            job_id,
            {
                "status": "succeeded",
                "finished_at": db.now_iso(),
                "progress": 1.0,
                "stage": "done",
                "provider": usage.provider,
                "gpu": usage.gpu,
                "gpu_seconds": round(usage.gpu_seconds, 2),
                "cost_usd": usage.cost_usd(),
                "simulated": bool(simulated),
                "error": fallback or None,
            },
        )
        ctx.log("Terminé" + (f" ({output.notes})" if output.notes else ""), progress=1.0, stage="done")
    except EngineUnavailable as exc:
        _fail(job, ctx, f"moteur indisponible: {exc}", started_wall, billable=True)
    except Exception as exc:
        _fail(job, ctx, f"{exc.__class__.__name__}: {exc}", started_wall, billable=True)
    finally:
        with _lock:
            _running.discard(job_id)


def _fail(job: dict[str, Any], ctx: Ctx, message: str, started_wall: float, billable: bool) -> None:
    wall = time.time() - started_wall
    if billable and wall > 2.0:
        # a failed GPU attempt still burns rented time: account for it
        cost.record(
            job["project_id"],
            job["id"],
            cost.Usage(provider=job.get("provider", "local"), gpu=job.get("gpu", "CPU"), gpu_seconds=wall,
                       notes="tentative échouée"),
            note="échec",
        )
    db.update(
        "jobs",
        job["id"],
        {"status": "failed", "finished_at": db.now_iso(), "error": message[-4000:], "stage": "failed"},
    )
    ctx.log(f"ÉCHEC: {message}")


def _dispatch(job: dict[str, Any], ctx: Ctx) -> tuple[EngineOutput, str, str, bool]:
    job_type = job["type"]
    params = dict(job.get("params") or {})
    project = db.get("projects", job["project_id"]) if job.get("project_id") else {}
    shot = db.get("shots", job["shot_id"]) if job.get("shot_id") else {}

    if job_type == "assembly":
        return _run_assembly(job, params, project or {}, ctx)

    if job_type == "retake":
        return _run_retake(job, params, shot or {}, ctx)

    kind = {"video": "video", "image": "image", "tts": "tts", "avatar": "avatar"}[job_type]
    requested = params.get("engine") or (job.get("engine") if job.get("engine") not in (None, "auto") else None)
    engine, fallback = registry.resolve(kind, requested)
    if fallback:
        ctx.log(f"Repli moteur: {fallback}", stage="engine")
    simulated = engine.info.simulated
    engine, requested_name, engine_fallback, sim = engine, engine.info.name, fallback, simulated

    output_dir = _output_dir(job)
    inputs: dict[str, Any] = {}

    # avatar shots need a voice first: run TTS inside the same job
    if job_type == "avatar":
        audio_artifact = _latest_artifact(job["shot_id"], kinds=("audio",))
        if audio_artifact and not params.get("force_tts"):
            inputs["audio_path"] = audio_artifact["path"]
            ctx.log("Voix existante réutilisée", stage="tts")
        else:
            tts_params = dict(params.get("tts") or {})
            tts_params.setdefault("text", shot.get("dialogue", ""))
            if not str(tts_params.get("text", "")).strip():
                raise ValueError("plan avatar sans dialogue: écrire le texte avant de générer")
            voice = db.get("voices", shot.get("voice_id")) if shot.get("voice_id") else None
            if voice:
                tts_params.setdefault("ref_audio", voice.get("ref_audio"))
                tts_params.setdefault("language", voice.get("language", "fr"))
                tts_params.setdefault("engine", voice.get("engine"))
            tts_engine, tts_fallback = registry.resolve("tts", tts_params.get("engine"))
            if tts_fallback:
                engine_fallback = (engine_fallback + "; " + tts_fallback).strip("; ")
            ctx.log(f"Voix: {tts_engine.info.name}", progress=0.1, stage="tts")
            tts_request = EngineRequest(
                kind="tts", output_dir=output_dir / "voice", project=project or {}, shot=shot or {},
                params={**tts_params, "text": tts_params.get("text")}, inputs=inputs,
            )
            tts_output = tts_engine.run(tts_request, ctx)
            tts_artifacts = _register_artifacts(job, tts_output, kind_override="audio")
            if not tts_artifacts:
                raise RuntimeError("le moteur de voix n'a produit aucun fichier")
            inputs["audio_path"] = tts_artifacts[0]["path"]
            sim = sim or tts_engine.info.simulated

        reference = params.get("reference_image") or _character_reference(shot)
        if reference:
            inputs["reference_image"] = reference
        else:
            ctx.log("Aucune image de référence: renseigner une image de personnage pour un avatar fidèle",
                    stage="engine")

    request_params = {**params}
    request_params.pop("engine", None)
    request_params.setdefault("duration_s", shot.get("duration_s"))
    request = EngineRequest(
        kind=kind, output_dir=output_dir, project=project or {}, shot=shot or {},
        params=request_params, inputs=inputs,
    )
    if job_type == "video":
        request.params.setdefault("prompt", shot.get("prompt", ""))
        if not request.params.get("prompt"):
            raise ValueError("plan sans prompt vidéo")
    noise = min(1.0, 0.85 + len(project.get("brief", "")) % 100 / 1000)
    ctx.log(f"Moteur: {requested_name} ({'simulé' if sim else 'réel'})", progress=0.05 * noise, stage="engine")
    output = engine.run(request, ctx)
    if isinstance(output, tuple):  # pragma: no cover - defensive
        output = output[0]
    return output, requested_name, engine_fallback, sim


def _run_assembly(job: dict[str, Any], params: dict[str, Any], project: dict[str, Any], ctx: Ctx) -> tuple[EngineOutput, str, str, bool]:
    shots = db.find("shots", "project_id = ?", (project["id"],), order="idx ASC")
    if not shots:
        raise ValueError("projet sans plan: impossible de monter")
    clips, missing = [], []
    for shot in shots:
        artifact = None
        if shot.get("selected_artifact"):
            artifact = db.get("artifacts", shot["selected_artifact"])
        if artifact is None:
            artifact = _latest_artifact(shot["id"], kinds=("video",))
        if artifact is None:
            missing.append(f"plan {shot['idx'] + 1} ({shot.get('title') or shot.get('kind')})")
            continue
        clips.append(
            {
                "path": artifact["path"],
                "duration_s": shot.get("duration_s"),
                "dialogue": shot.get("dialogue", ""),
                "title": shot.get("title", ""),
                "kind": shot.get("kind", "b_roll"),
                "transition": shot.get("transition", "cut"),
            }
        )
    if missing:
        raise ValueError("plans sans vidéo: " + ", ".join(missing))

    spec = {
        "format": params.get("format") or project.get("format", "9:16"),
        "fps": int(params.get("fps") or 30),
        "subtitles": bool(params.get("subtitles", True)),
        "transitions": bool(params.get("transitions", True)),
        "loudness_target": float(params.get("loudness_target") or -14.0),
        "music_path": params.get("music_path") or project.get("music_path"),
        "music_gain_db": float(params.get("music_gain_db", -20.0)),
        "title_card": bool(params.get("title_card", False)),
    }
    engine = AssemblyEngine()
    request = EngineRequest(
        kind="assembly", output_dir=_output_dir(job), project=project,
        params={**spec, "shot_labels": bool(params.get("shot_labels", False))},
        inputs={"clips": clips},
    )
    output = engine.run(request, ctx)
    primary = next((a for a in output.artifacts if a["kind"] == "export"), None)
    if primary is None:
        raise RuntimeError("le montage n'a produit aucun export")
    inspection = qc.inspect_export(primary["path"], spec, expected_duration_s=output.diagnostics.get("duration_s"))
    db.insert(
        "exports",
        {
            "id": db.new_id("exp"),
            "project_id": project["id"],
            "job_id": job["id"],
            "path": primary["path"],
            "spec": spec,
            "duration_s": output.diagnostics.get("duration_s", 0),
            "qc": inspection,
            "created_at": db.now_iso(),
        },
    )
    db.update("projects", project["id"], {"status": "exported"})
    ctx.log(f"Export prêt ({output.diagnostics.get('duration_s')}s, QC {inspection['verdict']})", progress=0.99)
    return output, "ffmpeg_assembly", "", False


def _run_retake(job: dict[str, Any], params: dict[str, Any], shot: dict[str, Any], ctx: Ctx) -> tuple[EngineOutput, str, str, bool]:
    artifact = db.get("artifacts", params.get("artifact_id", ""))
    if not artifact:
        raise ValueError("retake: artefact source introuvable")
    params["video_path"] = artifact["path"]
    engine, fallback = registry.resolve("video", params.get("engine") or "ltx_native")
    if engine.info.simulated:
        raise EngineUnavailable("le retake nécessite un moteur vidéo réel (LTX)")
    request = EngineRequest(
        kind="video", output_dir=_output_dir(job), project={}, shot=shot,
        params=params, inputs={"video_path": artifact["path"]},
    )
    output = engine.run_retake(request, ctx)  # type: ignore[attr-defined]
    replacement = output.artifacts[0]["path"]
    spliced = request.out("spliced.mp4")
    ctx.log("Réinsertion de la zone régénérée", progress=0.95, stage="splice")
    splice_region(artifact["path"], replacement, float(params["start_s"]), float(params["end_s"]), spliced)
    output.artifacts.insert(0, {"path": str(spliced), "kind": "video", "mime": "video/mp4",
                                "bytes": spliced.stat().st_size, "meta": {"retake": True}})
    return output, engine.info.name, fallback, False


# ----------------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------------
def _output_dir(job: dict[str, Any]) -> Path:
    settings = get_settings()
    if job.get("project_id"):
        base = settings.data_dir / "projects" / job["project_id"] / "jobs"
    else:
        base = settings.data_dir / "tmp"
    return base / job["id"]


def _register_artifacts(job: dict[str, Any], output: EngineOutput, kind_override: str | None = None) -> list[dict[str, Any]]:
    registered = []
    for item in output.artifacts:
        path = Path(item["path"])
        stored = db.insert(
            "artifacts",
            {
                "id": db.new_id("art"),
                "job_id": job["id"],
                "project_id": job.get("project_id"),
                "shot_id": job.get("shot_id"),
                "kind": kind_override or item.get("kind", "file"),
                "path": str(path),
                "mime": item.get("mime", "application/octet-stream"),
                "bytes": item.get("bytes") or (path.stat().st_size if path.exists() else 0),
                "meta": {**(item.get("meta") or {}), "simulated": bool(item.get("meta", {}).get("simulated"))},
                "created_at": db.now_iso(),
            },
        )
        registered.append(stored)
    return registered


def _primary_artifact(artifacts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for kind in ("video", "audio", "image", "export"):
        for artifact in artifacts:
            if artifact["kind"] == kind:
                return artifact
    return artifacts[0] if artifacts else None


def _link_shot(job: dict[str, Any], primary: dict[str, Any] | None, output: EngineOutput, simulated: bool) -> None:
    shot_id = job.get("shot_id")
    if not shot_id or primary is None:
        return
    shot = db.get("shots", shot_id)
    if shot is None:
        return
    patch: dict[str, Any] = {"updated_at": db.now_iso()}
    if primary["kind"] == "video":
        patch["selected_artifact"] = primary["id"]
        patch["status"] = "generated"
        inspection = qc.inspect_clip(primary["path"], expected_duration_s=shot.get("duration_s"))
        inspection["simulated"] = simulated
        patch["qc"] = inspection
    elif primary["kind"] == "audio":
        patch["status"] = "voiced" if shot.get("status") == "draft" else shot.get("status")
    db.update("shots", shot_id, patch)


def _link_export_assets(job: dict[str, Any], artifacts: list[dict[str, Any]]) -> None:
    """Attach poster and subtitle artifact ids to the export row for the UI."""
    exports = db.find("exports", "job_id = ?", (job["id"],))
    if not exports:
        return
    export = exports[0]
    spec = dict(export.get("spec") or {})
    for artifact in artifacts:
        if artifact["kind"] == "poster":
            spec["poster_artifact"] = artifact["id"]
        elif artifact["kind"] == "subtitles":
            spec["srt_artifact"] = artifact["id"]
    db.update("exports", export["id"], {"spec": spec})


def _latest_artifact(shot_id: str | None, kinds: tuple[str, ...] = ()) -> dict[str, Any] | None:
    if not shot_id:
        return None
    rows = db.find("artifacts", "shot_id = ?", (shot_id,), order="created_at DESC")
    for row in rows:
        if not kinds or row["kind"] in kinds:
            return row
    return None


def _character_reference(shot: dict[str, Any]) -> str | None:
    character_id = shot.get("character_id")
    if not character_id:
        return None
    character = db.get("characters", character_id)
    if not character:
        return None
    return character.get("base_image")


def job_log_tail(job_id: str, lines: int = 80) -> str:
    path = log_path(job_id)
    if not path.exists():
        return ""
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-lines:])
    except OSError:
        return ""


def stats() -> dict[str, Any]:
    rows = db.find("jobs", "", order="created_at DESC", limit=200)
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    total_cost = (db.fetchone("SELECT COALESCE(SUM(usd), 0) AS s FROM cost_events") or {"s": 0})["s"]
    return {"jobs": len(rows), "by_status": by_status, "cost_usd": round(total_cost, 4),
            "workers": get_settings().max_workers, "active": len(_running)}
