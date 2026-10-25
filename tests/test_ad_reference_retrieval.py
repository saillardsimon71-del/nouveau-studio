import json
from collections import Counter

import pytest

from app.ad_references.library import Library, default_root
from app.ad_references.models import Reference


def test_catalog_has_exactly_fifteen_honest_references():
    library = Library()
    assert len(library.references) == 15
    assert Counter(r.category for r in library.references) == {
        "ugc_presenter": 5, "premium_beauty": 3, "premium_fashion": 3,
        "storytelling": 2, "product_demo": 2,
    }
    for reference in library.references:
        assert reference.source.url.startswith("https://")
        assert reference.source.analysis_access == "metadata_only"
        assert reference.source.media_authorized is False
        assert reference.voice == {}
        assert reference.source.verification_date == "2026-10-25"
        assert all(o.basis == "source_description" for o in reference.observations)


def test_retrieval_is_bounded_and_explains_documentary_basis():
    context = Library().retrieve("UGC cosmétique avec présentatrice française")
    assert context["category"] == "ugc_presenter"
    assert len(context["references"]) <= 3
    assert len(context["recipes"]) == 1
    assert context["recipes"][0]["basis"] == "source_description"
    assert len(json.dumps(context, ensure_ascii=False)) < 6000
    assert "transcript" not in json.dumps(context)


def test_unknown_or_missing_catalog_is_an_empty_context(tmp_path):
    assert Library(tmp_path).retrieve("aucune catégorie") == {}
    assert Library().retrieve("une automatisation des e-mails") == {}


def test_invalid_catalog_is_rejected_and_duplicate_ids_are_rejected(tmp_path):
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog" / "broken.json").write_text("{}")
    with pytest.raises(ValueError):
        Library(tmp_path)
    sample = json.loads(next((default_root() / "catalog").glob("*.json")).read_text(encoding="utf-8"))
    (tmp_path / "catalog" / "broken.json").write_text(json.dumps(sample))
    (tmp_path / "catalog" / "duplicate.json").write_text(json.dumps(sample))
    with pytest.raises(ValueError, match="duplicate"):
        Library(tmp_path)


def test_video_observations_require_timestamps_and_confidence():
    sample = Library().references[0].model_dump()
    sample["observations"] = [{"id": "bad", "domain": "visual", "value": "smile",
                               "basis": "video_observation", "confidence": 0.8,
                               "evidence": {"locator": "frame.jpg"}}]
    with pytest.raises(ValueError, match="timestamp"):
        Reference.model_validate(sample)


def test_large_annotations_cannot_expand_director_context():
    library = Library()
    for reference in library.references:
        for observation in reference.observations:
            observation.value = "Long annotation " * 2000
    for recipe in library.recipes:
        for rule in recipe.rules:
            rule["instruction"] = "Long rule " * 2000
    assert len(json.dumps(library.retrieve("UGC"), ensure_ascii=False)) <= 6000


def test_imported_analysis_becomes_retrievable_measured_recipe(tmp_path, monkeypatch):
    from app.ad_references.library import import_analysis
    analysis = {"source": {"path": "own.mp4", "sha256": "f" * 64,
                           "authorization_evidence": "our production"}, "duration_seconds": 5,
                "voice": {"words_per_minute_speech_span": 160, "transcription_source": "whisper_local_cpu"},
                "visual": {"shots": [{"start_s": 0, "end_s": 5}]}, "limitations": []}
    import_analysis(analysis, "own", "ugc_presenter", "Own", "Own", tmp_path)
    context = Library(tmp_path).retrieve("UGC")
    assert context["recipes"][0]["basis"] == "analyzed_media"
    assert context["measured_pace_wpm"] == 160
    with pytest.raises(ValueError, match="already exists"):
        import_analysis(analysis, "own", "ugc_presenter", "Own", "Own", tmp_path)


def test_unverified_transcript_cannot_become_a_measured_voice_recipe(tmp_path):
    from app.ad_references.library import import_analysis
    report = {"source": {"path": "own.mp4", "sha256": "a" * 64, "authorization_evidence": "own"},
              "duration_seconds": 5, "voice": {"transcription_source": "supplied_transcript_unverified",
              "words_per_minute_speech_span": 800}, "visual": {"shots": []}, "limitations": []}
    imported = import_analysis(report, "own", "ugc_presenter", "Own", "Own", tmp_path)
    assert not any(o.domain == "voice" and o.basis == "acoustic_measurement" for o in imported.observations)
    assert "800" not in json.dumps(Library(tmp_path).retrieve("UGC")["recipes"])


def test_missing_recipe_instruction_falls_back_in_director(tmp_path, monkeypatch):
    from app.director import propose
    root = default_root()
    (tmp_path / "catalog").mkdir()
    (tmp_path / "recipes").mkdir()
    recipe = json.loads((root / "recipes" / "presenter_documentary_v1.json").read_text(encoding="utf-8"))
    recipe["rules"][0].pop("instruction")
    (tmp_path / "recipes" / "invalid.json").write_text(json.dumps(recipe))
    for rid in recipe["reference_ids"]:
        (tmp_path / "catalog" / f"{rid}.json").write_bytes((root / "catalog" / f"{rid}.json").read_bytes())
    monkeypatch.setenv("PVS_AD_REFERENCE_DIR", str(tmp_path))
    result = propose("UGC", use_llm=False, use_references=True)
    assert result.reference_context == {}
    assert "Bibliothèque indisponible" in result.notes


def test_authorized_reference_requires_authorization_evidence():
    sample = Library().references[0].model_dump()
    sample["source"].update(media_authorized=True, analysis_access="full_video")
    with pytest.raises(ValueError, match="authorization evidence"):
        Reference.model_validate(sample)
