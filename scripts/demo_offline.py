#!/usr/bin/env python3
"""Offline end-to-end demo — proves the studio pipelines, not the models.

Creates a 35-second vertical project from the brief, generates every shot with
the simulation engine, synthesises a neutral music bed, exports with burned-in
subtitles, then prints the QC report and the artifact paths.

Everything produced here is labelled SIMULATION: no AI model runs. Use it to
validate project structure, job orchestration, subtitling, mixing and export —
and as the fixture for the UI.

    PYTHONPATH=backend ./.venv/bin/python scripts/demo_offline.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app import media  # noqa: E402
from app.main import app  # noqa: E402

BRIEF = (
    "Crée une publicité Instagram de 35 secondes avec mon avatar. Il présente une automatisation "
    "qui trie les e-mails et prépare des réponses. Style technologique premium, en français."
)


def music_bed(path: Path, seconds: float = 40.0) -> Path:
    """A quiet ambient pad so the mix path is really exercised (no AI music)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    graph = (
        f"sine=frequency=110:sample_rate=48000:duration={seconds}[a];"
        f"sine=frequency=165:sample_rate=48000:duration={seconds}[b];"
        f"sine=frequency=220:sample_rate=48000:duration={seconds}[c];"
        "[a][b][c]amix=inputs=3:normalize=1,tremolo=f=0.15:d=0.35,"
        "lowpass=f=900,volume=0.5,afade=t=in:st=0:d=3,"
        f"afade=t=out:st={seconds - 4}:d=4,"
        "aformat=channel_layouts=stereo[m]"
    )
    media.run_ffmpeg(["-filter_complex", graph, "-map", "[m]", "-c:a", "pcm_s16le", str(path)], timeout=300)
    return path


def wait(client: TestClient, job_id: str, label: str) -> dict:
    started = time.time()
    while time.time() - started < 900:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            print(f"   {label:22} {job['status']:9} {time.time() - started:5.1f}s  {job.get('stage', '')}")
            return job
        time.sleep(0.5)
    raise TimeoutError(label)


def main() -> int:
    with TestClient(app) as client:
        system = client.get("/api/system").json()
        print("Moteurs réels disponibles :", [e["name"] for e in system["engines"] if e["available"] and not e["simulated"]])
        print("Blocages :", *[f"\n  - {b}" for b in system["blockers"]], sep="")

        project = client.post("/api/projects", json={"name": "Démo — automatisation e-mails", "brief": BRIEF}).json()
        print(f"\nProjet {project['id']}")

        proposal = client.post("/api/director/propose", json={"brief": BRIEF, "target_duration_s": 35}).json()
        print(f"Storyboard : {proposal['source']} ({len(proposal['storyboard']['shots'])} plans)")
        board = client.post(
            f"/api/projects/{project['id']}/storyboard",
            json=proposal["storyboard"],
        ).json()
        print(f"Durée planifiée : {board['total_duration_s']}s")

        print("\nGénération (simulation) :")
        for shot in board["shots"]:
            job = client.post(f"/api/shots/{shot['id']}/generate", json={}).json()
            final = wait(client, job["id"], f"plan {shot['idx'] + 1} · {shot['kind']}")
            if final["status"] != "succeeded":
                print("   échec:", final.get("error"))
                return 1

        bed = music_bed(Path(system["data_dir"]) / "assets" / "music" / "demo_bed.wav")
        print(f"\nNappe musicale : {bed}")

        print("\nMontage :")
        export_job = client.post(
            f"/api/projects/{project['id']}/export",
            json={
                "music_path": str(bed),
                "music_gain_db": -24,
                "subtitles": True,
                "transitions": True,
                "title_card": True,
                "format": "9:16",
                "fps": 30,
            },
        ).json()
        final = wait(client, export_job["id"], "export")
        if final["status"] != "succeeded":
            print(final.get("log", ""))
            return 1

        project = client.get(f"/api/projects/{project['id']}").json()
        export = project["exports"][0]
        print(f"\nExport : {export['path']}")
        print(f"  durée {export['duration_s']}s · QC {export['qc']['verdict']}")
        for check in export["qc"]["checks"]:
            print(f"    {check['status']:6} {check['id']:20} {check['detail']}")
        print("\n  Vérifications humaines restantes :")
        for item in export["qc"]["human_checks"]:
            print(f"    - {item}")
        print(f"\n  Coût enregistré : {project['cost']['cost_usd']} $ · jobs {project['cost']['jobs']}")
        print(f"  Projet visible dans l'UI : /#/project/{project['id']}")
        print("\nRAPPEL : ces clips sont des plaques de test, pas des sorties de modèle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
