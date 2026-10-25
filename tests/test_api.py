from __future__ import annotations

import io

from conftest import wait_job

from app import media


def test_health_and_system(client):
    assert client.get("/api/health").json()["ok"] is True
    system = client.get("/api/system").json()
    names = {engine["name"] for engine in system["engines"]}
    assert {"ltx_native", "longcat_avatar", "chatterbox", "ffmpeg_assembly", "mock"} <= names
    assert system["ffmpeg"].startswith("ffmpeg")
    # in this environment the real engines must be reported unavailable, not hidden
    assert system["blockers"]
    assert any("LTX" in blocker for blocker in system["blockers"])


def test_storyboard_roundtrip(client, project):
    proposal = client.post(
        "/api/director/propose", json={"brief": project["brief"], "target_duration_s": 35}
    ).json()
    assert proposal["source"] == "heuristic"

    applied = client.post(f"/api/projects/{project['id']}/storyboard", json=proposal["storyboard"])
    assert applied.status_code == 200
    body = applied.json()
    assert len(body["shots"]) == len(proposal["storyboard"]["shots"])
    assert body["shots"][0]["idx"] == 0
    assert body["total_duration_s"] > 30
    # avatar shots get the first known character (none yet) and stay editable
    assert body["shots"][1]["kind"] == "avatar"


def test_generate_simulated_video_and_qc(client, project):
    proposal = client.post("/api/director/propose", json={"brief": project["brief"]}).json()
    board = client.post(f"/api/projects/{project['id']}/storyboard", json=proposal["storyboard"]).json()
    shot = board["shots"][0]

    job = client.post(f"/api/shots/{shot['id']}/generate", json={}).json()
    assert job["status"] == "queued"
    final = wait_job(client, job["id"])

    assert final["status"] == "succeeded", final.get("error")
    # the mock fallback must be flagged, never disguised as model output
    assert final["simulated"] == 1
    assert "simulation" in (final["error"] or "").lower()

    refreshed = client.get(f"/api/projects/{project['id']}").json()
    shot_after = refreshed["shots"][0]
    assert shot_after["selected_artifact"]
    assert shot_after["qc"]["verdict"] in {"pass", "review"}
    assert shot_after["qc"]["simulated"] is True
    assert shot_after["qc"]["human_checks"]

    artifact = client.get(f"/api/artifacts/{shot_after['selected_artifact']}").json()
    info = media.probe(artifact["path"])
    assert (info.width, info.height) == (1080, 1920)
    assert info.has_audio


def test_avatar_shot_generates_voice_then_video(client, project):
    board = client.post(
        f"/api/projects/{project['id']}/storyboard",
        json={
            "concept": "t",
            "script": "",
            "style_guide": "",
            "shots": [
                {
                    "kind": "avatar",
                    "title": "Présentateur",
                    "duration_s": 2.5,
                    "dialogue": "Et si tu pouvais automatiser toutes ces tâches ?",
                    "prompt": "photorealistic presenter speaking to camera, dark studio",
                    "camera": "85mm",
                    "transition": "cut",
                    "engine_hint": "avatar",
                    "notes": "",
                }
            ],
        },
    ).json()
    shot = board["shots"][0]
    job = client.post(f"/api/shots/{shot['id']}/generate", json={}).json()
    final = wait_job(client, job["id"])
    assert final["status"] == "succeeded", final.get("error")

    artifacts = client.get(f"/api/jobs/{job['id']}").json()["artifacts"]
    kinds = [artifact["kind"] for artifact in artifacts]
    assert "audio" in kinds and "video" in kinds

    log = client.get(f"/api/jobs/{job['id']}/log").text
    assert "Voix:" in log


def test_avatar_without_dialogue_is_rejected(client, project):
    board = client.post(
        f"/api/projects/{project['id']}/storyboard",
        json={"concept": "", "script": "", "style_guide": "",
              "shots": [{"kind": "avatar", "title": "muet", "duration_s": 2, "dialogue": "",
                         "prompt": "x", "camera": "", "transition": "cut", "engine_hint": "", "notes": ""}]},
    ).json()
    shot = board["shots"][0]
    response = client.post(f"/api/shots/{shot['id']}/generate", json={})
    assert response.status_code == 400


def test_full_export_flow(client, project):
    proposal = client.post("/api/director/propose", json={"brief": project["brief"], "target_duration_s": 12}).json()
    client.post(f"/api/projects/{project['id']}/storyboard", json=proposal["storyboard"])
    board = client.get(f"/api/projects/{project['id']}").json()

    for shot in client.post(
        f"/api/projects/{project['id']}/storyboard",
        json=proposal["storyboard"],
    ).json()["shots"]:
        job = client.post(f"/api/shots/{shot['id']}/generate", json={'params': {'performance_mode': 'legacy'}}).json()
        assert wait_job(client, job["id"], timeout=240)["status"] == "succeeded"

    export_job = client.post(
        f"/api/projects/{project['id']}/export",
        json={"subtitles": True, "transitions": True, "music_gain_db": -22},
    ).json()
    final = wait_job(client, export_job["id"], timeout=300)
    assert final["status"] == "succeeded", final.get("error")

    exports = client.get(f"/api/projects/{project['id']}/exports").json()
    assert len(exports) == 1
    export = exports[0]
    assert export["qc"]["verdict"] in {"pass", "review"}
    assert export["duration_s"] > 8

    download = client.get(f"/api/exports/{export['id']}/file")
    assert download.status_code == 200
    assert download.headers["content-type"] == "video/mp4"
    assert len(download.content) > 100_000

    assert "poster_artifact" in export["spec"]
    poster = client.get(f"/api/artifacts/{export['spec']['poster_artifact']}/file")
    assert poster.status_code == 200


def test_export_blocked_when_shot_missing(client, project):
    proposal = client.post("/api/director/propose", json={"brief": project["brief"], "target_duration_s": 10}).json()
    client.post(f"/api/projects/{project['id']}/storyboard", json=proposal["storyboard"])
    job = client.post(f"/api/projects/{project['id']}/export", json={}).json()
    final = wait_job(client, job["id"], timeout=60)
    assert final["status"] == "failed"
    assert "plans sans vidéo" in final["error"]


def test_upload_rejects_unknown_extension(client, project):
    board = client.post(
        f"/api/projects/{project['id']}/shots",
        json={"kind": "b_roll", "title": "x", "duration_s": 2, "prompt": "p"},
    ).json()
    response = client.post(
        f"/api/shots/{board['id']}/upload?kind=video",
        files={"file": ("malware.exe", io.BytesIO(b"nope"), "application/octet-stream")},
    )
    assert response.status_code == 415


def test_upload_video_becomes_selected_artifact(client, project, tmp_path):
    board = client.post(
        f"/api/projects/{project['id']}/shots",
        json={"kind": "screen_capture", "title": "capture", "duration_s": 1.5, "prompt": "screen"},
    ).json()
    clip = tmp_path / "upload.mp4"
    media.run_ffmpeg(
        ["-f", "lavfi", "-i", "color=c=0x101820:s=1080x1920:d=1.5:r=30",
         "-f", "lavfi", "-i", "sine=frequency=300:duration=1.5",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)],
        timeout=120,
    )
    with clip.open("rb") as handle:
        response = client.post(
            f"/api/shots/{board['id']}/upload?kind=video",
            files={"file": ("capture.mp4", handle, "video/mp4")},
        )
    assert response.status_code == 200, response.text
    artifact = response.json()
    assert artifact["qc"]["verdict"] in {"pass", "review"}


def test_job_cancel_marks_cancelled(client, project):
    board = client.post(
        f"/api/projects/{project['id']}/shots",
        json={"kind": "b_roll", "title": "c", "duration_s": 2, "prompt": "p"},
    ).json()
    job = client.post(f"/api/shots/{board['id']}/generate", json={}).json()
    cancelled = client.post(f"/api/jobs/{job['id']}/cancel").json()
    assert cancelled["status"] in {"cancelled", "succeeded"}


def test_character_and_voice_references_roundtrip(client):
    """Uploads must be addressable by artifact id (that is what the UI stores)."""
    character = client.post(
        "/api/characters", json={"name": "Camille", "description": "présentatrice", "appearance": {}}
    ).json()

    png = (
        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        + b"\x90wS\xde" + b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    updated = client.post(
        f"/api/characters/{character['id']}/image",
        files={"file": ("ref.png", io.BytesIO(png), "image/png")},
    ).json()
    assert updated["base_image"].startswith("art_")
    served = client.get(f"/api/artifacts/{updated['base_image']}/file")
    assert served.status_code == 200
    assert served.content == png

    voice = client.post("/api/voices", json={"name": "Voix FR", "engine": "chatterbox", "language": "fr"}).json()
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 8000)
    sample = client.post(
        f"/api/voices/{voice['id']}/sample",
        files={"file": ("sample.wav", io.BytesIO(buffer.getvalue()), "audio/wav")},
    ).json()
    assert sample["ref_audio"].startswith("art_")
    assert client.get(f"/api/artifacts/{sample['ref_audio']}/file").status_code == 200
    assert sample["params"]["sample_seconds"] > 0.3
