"""Application entry point.

One process serves the API, the built UI and the generated media. No reverse
proxy, no CORS configuration, no separate worker service. On a GPU host the same
process spawns the model CLIs.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import db, jobs
from .api import router
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pvs")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    jobs.start()
    settings = get_settings()
    log.info("Premium Video Studio — data=%s workers=%s", settings.data_dir, settings.max_workers)
    yield
    jobs.shutdown()


app = FastAPI(title="Premium Video Studio", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # single-origin deployment; opened for the Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/api")
def api_root() -> dict[str, str]:
    return {"name": "Premium Video Studio", "docs": "/docs", "health": "/api/health"}


def _index() -> FileResponse:
    index = get_settings().static_dir / "index.html"
    if not index.exists():
        raise HTTPException(
            503,
            "Interface non compilée. Lancer `cd frontend && npm install && npm run build`, "
            "ou utiliser `npm run dev` en développement.",
        )
    return FileResponse(index)


@app.get("/")
def root() -> FileResponse:
    return _index()


@app.get("/{full_path:path}", response_model=None)
def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "not found"}, status_code=404)
    candidate = get_settings().static_dir / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    return _index()


def run() -> None:  # pragma: no cover - console entry
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, factory=False)


if __name__ == "__main__":  # pragma: no cover
    run()
