import pytest

from app.director import propose
from app.ad_references.performance import dialogue_plan


@pytest.mark.parametrize("brief,category", [
    ("UGC cosmétique, présentatrice française, sérum, 20 secondes", "ugc_presenter"),
    ("Vêtements haut de gamme, manteau, 20 secondes", "premium_fashion"),
    ("Publicité narrative avec deux personnages, une tasse, 20 secondes", "storytelling"),
])
def test_director_produces_traceable_h3_prompts(brief, category):
    result = propose(brief, use_llm=False, use_references=True)
    assert result.reference_context["category"] == category
    assert result.reference_context["recipes"]
    assert sum(s.duration_s for s in result.storyboard.shots) == pytest.approx(20, abs=.2)
    for shot in result.storyboard.shots:
        assert 4 <= shot.duration_s <= 15
        assert shot.creative_provenance
        assert shot.engine_hint == "modal_h3"
        assert len(shot.prompt) <= 7000
        if shot.dialogue:
            assert "French" in shot.prompt
            assert shot.dialogue in shot.prompt
            assert shot.performance["timing"]["fits"]


def test_disabled_or_empty_library_preserves_existing_behavior(tmp_path, monkeypatch):
    brief = "une automatisation des mails de 35 secondes"
    original = propose(brief, use_llm=False)
    assert original.reference_context == {}
    monkeypatch.setenv("PVS_AD_REFERENCE_DIR", str(tmp_path))
    enabled = propose(brief, use_llm=False, use_references=True)
    assert enabled.storyboard == original.storyboard


def test_dialogue_that_cannot_fit_is_flagged_without_speeding_up():
    result = dialogue_plan("Une phrase beaucoup trop longue " * 10, 5, target_wpm=165)
    assert result["fits"] is False
    assert result["required_seconds"] > 5
    assert result["recommendation"] == "shorten_dialogue_or_extend_shot"


def test_api_persists_provenance_without_database_migration(client, project):
    response = client.post("/api/director/propose", json={
        "brief": "UGC cosmétique française 20 secondes", "use_llm": False, "use_references": True})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["reference_context"]["references"]
    applied = client.post(f"/api/projects/{project['id']}/storyboard", json=data["storyboard"])
    assert applied.status_code == 200, applied.text
    assert applied.json()["shots"][0]["params"]["creative_provenance"]


def test_llm_receives_only_bounded_context_and_recipe_affects_prompt(monkeypatch):
    import httpx
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "llm_api_key", "test-only")
    payloads = []

    def respond(request):
        import json
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "concept": "Sérum", "shots": [{"kind": "avatar", "title": "Hook", "duration_s": 5,
            "dialogue": "Une routine plus simple ?", "prompt": "Adult woman, eye level."}]})}}]})

    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw))
    result = propose("UGC cosmétique", target_duration_s=5, use_llm=True, use_references=True)
    assert "presenter_documentary_v1" in payloads[0]["messages"][1]["content"]
    assert "entre 4 et 12" in payloads[0]["messages"][0]["content"]
    assert "Tie a product benefit" in result.storyboard.shots[0].prompt
    assert result.storyboard.shots[0].kind == "b_roll"
    assert result.storyboard.shots[0].engine_hint == "modal_h3"


def test_invalid_library_falls_back_with_visible_note(tmp_path, monkeypatch):
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog" / "broken.json").write_text("{}")
    monkeypatch.setenv("PVS_AD_REFERENCE_DIR", str(tmp_path))
    result = propose("UGC cosmétique", use_llm=False, use_references=True)
    assert result.reference_context == {}
    assert "Bibliothèque indisponible" in result.notes


def test_narrative_keeps_two_speakers_when_character_is_selected():
    result = propose("Publicité narrative avec deux personnages, 20 secondes", use_llm=False,
                     use_references=True, character={"id": "char_alice", "name": "Alice"})
    speakers = [s.performance["speaker"] for s in result.storyboard.shots if s.dialogue]
    assert speakers == ["Alice", "B", "Alice"]
    assert result.storyboard.shots[0].character_id == "char_alice"
    assert result.storyboard.shots[1].character_id is None


def test_selected_character_photo_reaches_h3_video_request(client, project, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from app import jobs
    from app.engines.base import EngineOutput
    photo = Path(__file__).resolve().parents[1] / "benchmark_assets/character_reference.png"
    character = client.post("/api/characters", json={"name": "Selected", "base_image": str(photo)}).json()
    proposal = client.post("/api/director/propose", json={"brief": "UGC cosmétique 20 secondes",
        "character_id": character["id"], "use_llm": False, "use_references": True}).json()
    applied = client.post(f"/api/projects/{project['id']}/storyboard", json=proposal["storyboard"]).json()
    shot = applied["shots"][0]
    assert shot["character_id"] == character["id"]

    class RecordingEngine:
        info = SimpleNamespace(name="modal_h3", simulated=False)

        def run(self, request, ctx):
            return EngineOutput(diagnostics={"reference_image": request.inputs.get("reference_image")})

    class Context:
        def log(self, *args, **kwargs):
            pass

    monkeypatch.setattr(jobs.registry, "resolve", lambda *args: (RecordingEngine(), ""))
    output, *_ = jobs._dispatch({"id": "job_reference_test", "project_id": project["id"],
                                "shot_id": shot["id"], "type": "video", "params": {}}, Context())
    assert output.diagnostics["reference_image"] == str(photo)


def test_narrative_llm_speaker_roles_are_preserved_out_of_order():
    from app.ad_references.library import Library
    from app.ad_references.performance import enrich_storyboard
    from app.schemas import Storyboard, ShotSpec
    context = Library().retrieve("narrative avec deux personnages")
    board = Storyboard(shots=[
        ShotSpec(duration_s=5, dialogue="Oui, regarde.", performance={"speaker_role": "B"}),
        ShotSpec(duration_s=5, dialogue="Merci beaucoup.", performance={"speaker_role": "A"}),
    ])
    enriched = enrich_storyboard(board, context, {"name": "Alice"})
    assert [s.performance["speaker"] for s in enriched.shots] == ["B", "Alice"]


def test_narrative_does_not_guess_missing_speaker_role():
    from app.ad_references.library import Library
    from app.ad_references.performance import enrich_storyboard
    from app.schemas import Storyboard, ShotSpec
    with pytest.raises(ValueError, match="explicit speaker_role"):
        enrich_storyboard(Storyboard(shots=[ShotSpec(duration_s=5, dialogue="Bonjour")]),
                          Library().retrieve("narrative avec deux personnages"))
