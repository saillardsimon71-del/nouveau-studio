import math
import re

from ..schemas import ShotSpec, Storyboard


def words(text):
    return re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text, re.UNICODE)


def dialogue_plan(text, duration_s, target_wpm=165, pause_s=.4):
    if not math.isfinite(duration_s) or duration_s <= 0 or not 80 <= target_wpm <= 220:
        raise ValueError("invalid dialogue timing parameters")
    count = len(words(text))
    required = count * 60 / target_wpm + (pause_s if count else 0)
    fits = required <= duration_s
    return {"word_count": count, "target_wpm": target_wpm, "pause_budget_s": pause_s if count else 0,
            "required_seconds": round(required, 3), "available_seconds": duration_s, "fits": fits,
            "basis": "editorial_rule_not_reference_measurement",
            "recommendation": "fits" if fits else "shorten_dialogue_or_extend_shot"}


def local_storyboard(brief, target, category, character=None):
    if not 16 <= target <= 48:
        raise ValueError("Reference local templates require 16..48s (four H3 shots of 4..12s)")
    presenter = (character or {}).get("description") or "an adult French female presenter"
    if category == "premium_fashion":
        scenes = [
            ("Silhouette", "b_roll", "", "Adult model in the client's garment, full silhouette, natural balanced stance; slow dolly in"),
            ("Matière", "product", "", "Close-up of the actual garment fabric and stitching, a single gentle hand adjustment"),
            ("Mouvement", "b_roll", "", "Same model and outfit, one measured walking step, physically plausible fabric movement"),
            ("Signature", "product", "", "Same garment, composed medium shot, model settles and holds a calm gaze"),
        ]
    elif category == "storytelling":
        scenes = [
            ("Situation", "b_roll", "Tu as pensé à moi ?", "Two distinct adults A and B; A faces B, asks a warm question; B listens without speaking"),
            ("Réponse", "b_roll", "Oui. Regarde, c'est pour toi.", "Reverse medium close-up; B answers A and gently presents the client's product; A listens"),
            ("Réaction", "b_roll", "Tu me connais bien.", "Reaction close-up of A, recognizes the gesture, small genuine smile after answering; B silent"),
            ("Résolution", "product", "", "Two-shot of the same adults sharing a quiet moment, product visible between them"),
        ]
    elif category == "ugc_presenter":
        scenes = [
            ("Hook", "b_roll", "Votre routine mérite plus de simplicité, non ?", f"{presenter}, medium close-up, eye contact with the lens, curious eyebrow lift"),
            ("Démonstration", "product", "Regardez comment je l'utilise, tout simplement.", "Same presenter demonstrates the client's product with one clear, plausible hand movement"),
            ("Bénéfice à valider", "b_roll", "Un geste facile à intégrer au quotidien.", "Same presenter, relaxed shoulders, conversational delivery, small smile after the key phrase"),
            ("CTA", "product", "Découvrez les détails et choisissez votre routine.", "Same presenter presents the product steadily, direct gaze, warm invitation, holds final frame"),
        ]
    else:
        scenes = [
            ("Découverte", "product", "", "Close-up of the client's actual product in sculpted light"),
            ("Usage", "product", "", "One adult demonstrates the product in a clear physically plausible action"),
            ("Détail", "product", "", "Macro detail of the actual product; preserve material and geometry"),
            ("Signature", "product", "", "Product hero shot in the same lighting, restrained slow camera movement"),
        ]
    duration = round(target / 4, 2)
    shots = [ShotSpec(kind=kind, title=title, duration_s=duration, dialogue=dialogue,
                      prompt=f"Photorealistic commercial. {visual}. Client brief: {brief}. "
                             "Preserve identities and product from the supplied real reference photo. No generated text or logos.",
                      camera="eye level, restrained camera movement", engine_hint="modal_h3",
                      performance={"speaker_role": "B" if category == "storytelling" and index == 1 else "A"})
             for index, (title, kind, dialogue, visual) in enumerate(scenes)]
    shots[-1].duration_s = round(target - sum(s.duration_s for s in shots[:-1]), 2)
    return Storyboard(concept=brief, script=" ".join(s.dialogue for s in shots if s.dialogue),
                      style_guide="Reference-informed local template; claims and casting require client review.", shots=shots)


def enrich_storyboard(storyboard, context, character=None):
    recipe = context.get("recipes", [])[:1]
    rules = recipe[0]["rules"] if recipe else []
    for index, shot in enumerate(storyboard.shots):
        if shot.kind in {"screen_capture", "title"}:
            continue
        if shot.kind == "avatar":
            shot.kind = "b_roll"
        shot.engine_hint = "modal_h3"
        if not 4 <= shot.duration_s <= 15:
            raise ValueError(f"H3 shot {index + 1} must last 4..15 seconds")
        measured_pace = context.get("measured_pace_wpm")
        wpm = round(max(120, min(190, measured_pace))) if measured_pace else (150 if context["category"] == "storytelling" else 165)
        timing = dialogue_plan(shot.dialogue, shot.duration_s, target_wpm=wpm)
        if measured_pace:
            timing["basis"] = "reference_asr_segment_span_with_editorial_clamp_120_190"
            timing["observed_reference_wpm"] = measured_pace
            timing["reference_id"] = context["measured_pace_reference_id"]
        if not timing["fits"]:
            raise ValueError(f"Shot {index + 1}: dialogue requires {timing['required_seconds']}s; "
                             f"only {shot.duration_s}s available. Shorten text or extend the shot.")
        role = shot.performance.get("speaker_role") or shot.performance.get("speaker") or "A"
        if context["category"] == "storytelling" and shot.dialogue:
            if not shot.performance.get("speaker_role") and not shot.performance.get("speaker"):
                raise ValueError(f"Narrative shot {index + 1} needs an explicit speaker_role A or B")
            if role not in {"A", "B"}:
                raise ValueError("Narrative speaker_role must be A or B")
        speaker = ((character or {}).get("name") or "A") if role == "A" else "B"
        shot.character_id = (character or {}).get("id") if role == "A" else None
        shot.performance = {"speaker": speaker, "speaker_role": role,
                            "language": "fr", "accent": "contemporary metropolitan French",
                            "timbre": "warm conversational adult voice, no imitation of reference actor",
                            "intent": "curious question then reassurance" if index == 0 else "warm, engaged invitation",
                            "timing": timing}
        shot.creative_provenance = [
            {"decision": rule["instruction"], "recipe_id": recipe[0]["recipe_id"],
             "reference_id": rule["reference_id"], "observation_id": rule["observation_id"],
             "basis": recipe[0]["basis"]} for rule in rules[:3]]
        shot.creative_provenance.append({"decision": "speech timing and restrained acting directions",
                                         "basis": "editorial_rule", "rule_id": "natural_delivery_v1"})
        if shot.dialogue:
            if context["category"] == "storytelling":
                shot.prompt += f" Casting: A is {(character or {}).get('name') or 'adult A'}; B is a distinct adult with a separate voice."
            shot.prompt += (
                f' Speaker {speaker} speaks in French with a contemporary metropolitan French accent, '
                f'warm conversational timbre, approximately {wpm} words per minute: "{shot.dialogue}". '
                "Vary pitch across phrases; lift the question ending when applicable, then settle on the response. "
                "Use a short natural pause at punctuation, emphasize one meaningful word, allow a small audible breath. "
                "Synchronize mouth movement with speech; a slight eyebrow response, one motivated hand gesture, "
                "small smile after the phrase. Other visible characters listen without speaking. "
                "Keep the same voice across shots for this speaker; preserve the reference identity. "
                "No background narration and no competing voices."
            )
        else:
            shot.prompt += " No speech. Motivated, restrained expression and physically plausible gestures."
        if rules:
            shot.prompt += " Creative adaptation: " + " ".join(rule["instruction"] for rule in rules[:3])
            shot.notes = (shot.notes + " Recipe: " + recipe[0]["recipe_id"] +
                          " (" + recipe[0]["basis"] + "). Voice target basis: " + timing["basis"] + ".").strip()
        if len(shot.prompt) > 7000:
            raise ValueError("H3 prompt exceeds installed worker limit of 7000 characters")
    return storyboard
