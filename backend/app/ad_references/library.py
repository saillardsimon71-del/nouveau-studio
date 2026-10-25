import json
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .models import Recipe, Reference


def default_root():
    return Path(os.environ.get("PVS_AD_REFERENCE_DIR") or Path(__file__).resolve().parents[3] / "studio/ad-references")


def classify(brief):
    text = unicodedata.normalize("NFKD", brief.lower()).encode("ascii", "ignore").decode()
    for category, terms in [
        ("ugc_presenter", ("ugc", "face camera", "presentatrice", "presentateur")),
        ("storytelling", ("narrati", "storytelling", "deux personnages", "dialogue")),
        ("premium_fashion", ("vetement", "mode luxe", "fashion", "manteau", "haute couture")),
        ("premium_beauty", ("cosmetique", "parfum", "beaute", "serum")),
        ("product_demo", ("e-commerce", "ecommerce", "demonstration produit")),
    ]:
        if any(term in text for term in terms):
            return category
    return None


class Library:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else default_root()
        roots = [self.root]
        if root is None and not os.environ.get("PVS_AD_REFERENCE_DIR"):
            from ..config import get_settings
            roots.append(get_settings().data_dir / "ad-references")
        self.references = [Reference.model_validate_json(p.read_text(encoding="utf-8"))
                           for folder in roots for p in sorted((folder / "catalog").glob("*.json"))]
        self.recipes = [Recipe.model_validate_json(p.read_text(encoding="utf-8"))
                        for folder in roots for p in sorted((folder / "recipes").glob("*.json"))]
        by_id = {r.reference_id: r for r in self.references}
        if len(by_id) != len(self.references):
            raise ValueError("duplicate reference_id")
        for recipe in self.recipes:
            for reference_id in recipe.reference_ids:
                if reference_id not in by_id:
                    raise ValueError(f"unknown recipe reference: {reference_id}")
            for rule in recipe.rules:
                ref = by_id.get(rule.get("reference_id"))
                evidence = next((o for o in ref.observations if o.id == rule.get("observation_id")), None) if ref else None
                if evidence is None or ref.reference_id not in recipe.reference_ids:
                    raise ValueError("recipe rule requires a linked observation")
                if recipe.basis == "analyzed_media" and evidence.basis == "source_description":
                    raise ValueError("analyzed_media recipe cannot use documentary evidence")

    def retrieve(self, brief, category=None):
        category = category or classify(brief)
        matches = [r for r in self.references if r.category == category]
        if not matches:
            return {}
        recipes = sorted((r for r in self.recipes if r.category == category),
                         key=lambda r: (r.basis != "analyzed_media", r.recipe_id))[:1]
        selected_ids = recipes[0].reference_ids if recipes else []
        matches.sort(key=lambda r: (r.reference_id not in selected_ids, r.reference_id))
        selected = matches[:3]
        measured_reference = next((r for r in selected
                                   if r.source.media_authorized and r.source.analysis_access == "full_video"
                                   and r.voice.get("transcription_source") == "whisper_local_cpu"
                                   and r.voice.get("words_per_minute_speech_span")), None)
        measured_pace = measured_reference.voice["words_per_minute_speech_span"] if measured_reference else None
        context = {
            "category": category,
            "references": [{"reference_id": r.reference_id, "brand": r.brand[:80], "title": r.title[:140],
                            "url": r.source.url[:500], "access": r.source.analysis_access,
                            "insights": [{"id": o.id, "value": str(o.value)[:300], "basis": o.basis,
                                          "confidence": o.confidence, "evidence": {
                                              "locator": o.evidence.locator[:160],
                                              "start_s": o.evidence.start_s, "end_s": o.evidence.end_s,
                                              "media_sha256": o.evidence.media_sha256}}
                                         for o in r.observations[:2]]} for r in selected],
            "recipes": [{"recipe_id": r.recipe_id, "title": r.title[:160], "basis": r.basis,
                         "reference_ids": r.reference_ids[:3], "rules": [
                             {"instruction": str(rule["instruction"])[:300], "reference_id": rule["reference_id"],
                              "observation_id": rule["observation_id"]} for rule in r.rules[:3]]} for r in recipes],
            "measured_pace_wpm": measured_pace,
            "measured_pace_reference_id": measured_reference.reference_id if measured_reference else None,
            "limitations": ["Documentary patterns are provisional; measured patterns require editorial adaptation. No conversion claim."],
        }
        while len(json.dumps(context, ensure_ascii=False)) > 6000:
            populated = [r for r in context["references"] if r["insights"]]
            if not populated:
                raise ValueError("reference identifiers exceed Director context budget")
            populated[-1]["insights"].pop()
        return context


def derive_recipe(reference, recipe_id, title):
    reference = Reference.model_validate(reference)
    observations = [o for o in reference.observations
                    if o.basis in {"video_observation", "acoustic_measurement"} and o.confidence >= .7]
    if not reference.source.media_authorized or not observations:
        raise ValueError("authorized analyzed observations required")
    return Recipe(recipe_id=recipe_id, category=reference.category, title=title, basis="analyzed_media",
                  reference_ids=[reference.reference_id], rules=[
                      {"instruction": str(o.value), "reference_id": reference.reference_id,
                       "observation_id": o.id, "adaptation": "Observation to adapt, not a performance guarantee"}
                      for o in observations[:8]],
                  limitations=["One reference; transfer to another product requires editorial review."])


def import_analysis(analysis, reference_id, category, brand, title, library_root):
    from ..media import write_json
    root = Path(library_root)
    destination = root / "catalog" / f"{reference_id}.json"
    if destination.exists():
        raise ValueError("reference already exists; use a new reference_id for another version")
    source = analysis["source"]
    duration = analysis["duration_seconds"]
    voice = analysis["voice"]
    observations = list(analysis.get("observations", []))
    shots = analysis["visual"]["shots"]
    observations.append({"id": reference_id + "_rhythm", "domain": "visual",
                         "value": f"Observed {len(shots)} cut candidates over {duration}s; adapt shot pacing to the brief.",
                         "basis": "video_observation", "confidence": .7,
                         "evidence": {"locator": "analysis.json#/visual/shots", "start_s": 0, "end_s": duration,
                                      "media_sha256": source["sha256"]},
                         "uncertainty": "Threshold-based cuts, not human-verified transitions."})
    if voice.get("transcription_source") == "whisper_local_cpu" and voice.get("words_per_minute_speech_span"):
        observations.append({"id": reference_id + "_pace", "domain": "voice",
                             "value": f"Observed ASR segment-span pace: {voice['words_per_minute_speech_span']} words/minute.",
                             "basis": "acoustic_measurement", "confidence": .7,
                             "evidence": {"locator": "analysis.json#/voice", "start_s": 0, "end_s": duration,
                                          "media_sha256": source["sha256"]},
                             "uncertainty": "ASR-derived timing includes pauses; inspect transcription."})
    reference = Reference(reference_id=reference_id, category=category, brand=brand, title=title,
                          source={"url": "local:sha256:" + source["sha256"], "license": "operator_authorized",
                                  "rights_note": "Authorization is declared by the importing operator; no redistribution inferred.",
                                  "analysis_access": "full_video", "media_authorized": True,
                                  "authorization_evidence": source["authorization_evidence"],
                                  "verification_date": datetime.now(timezone.utc).date().isoformat(),
                                  "local_path": source["path"], "downloaded": False},
                          duration_seconds=duration, duration_basis="PyAV probe", platform="local authorized file",
                          ad_type="operator_import", concept="Awaiting editorial annotation", commercial_message="Unannotated",
                          voice=voice, observations=observations,
                          limitations=analysis["limitations"])
    write_json(destination, reference.model_dump())
    recipe = derive_recipe(reference.model_dump(), reference_id + "_observed", title + " - observed patterns")
    write_json(root / "recipes" / f"{recipe.recipe_id}.json", recipe.model_dump())
    return reference
