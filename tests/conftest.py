"""Test bootstrap: isolated data dir, mock engines allowed, no real GPU engines."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

_TMP = tempfile.mkdtemp(prefix="pvs-test-")
os.environ.setdefault("PVS_DATA_DIR", _TMP)
os.environ["PVS_ALLOW_MOCK"] = "1"
os.environ["PVS_MAX_WORKERS"] = "1"
os.environ["PVS_REQUEUE_ON_BOOT"] = "1"
os.environ["PVS_LLM_API_KEY"] = ""
os.environ["PVS_COMFY_URL"] = ""

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def project(client):
    response = client.post(
        "/api/projects",
        json={
            "name": "Automatisation e-mails",
            "brief": (
                "Crée une publicité Instagram de 35 secondes avec mon avatar. Il présente une "
                "automatisation qui trie les e-mails et prépare des réponses. Style technologique "
                "premium, en français."
            ),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_job(client, job_id: str, timeout: float = 180.0) -> dict:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.25)
    raise TimeoutError(f"job {job_id} toujours en cours")
