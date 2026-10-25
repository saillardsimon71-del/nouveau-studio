import argparse
import json
from pathlib import Path

from .. import media
from ..config import get_settings
from ..director import propose
from .analysis import analyze
from .evaluation import compare, evaluate
from .library import Library, import_analysis


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Local advertising reference tools. No video generation or remote API calls.")
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("--brief", default="")
    analysis = commands.add_parser("analyze")
    analysis.add_argument("media", type=Path)
    analysis.add_argument("--out", type=Path, required=True)
    analysis.add_argument("--authorized-use", required=True, help="Reason you are authorized to analyze this file")
    analysis.add_argument("--transcript", type=Path, help="Whisper/WhisperX JSON, timestamps in seconds")
    analysis.add_argument("--whisper-model", type=Path, help="Existing .pt checkpoint; never downloaded")
    analysis.add_argument("--language", default="fr")
    analysis.add_argument("--speech-only", action="store_true", help="Declare isolated speech; enables optional pitch analysis")
    analysis.add_argument("--observations", type=Path, help="Timed, media-hash-bound visual/marketing annotation list")
    ingestion = commands.add_parser("import")
    ingestion.add_argument("analysis", type=Path)
    ingestion.add_argument("--reference-id", required=True)
    ingestion.add_argument("--category", required=True,
                           choices=["ugc_presenter", "premium_fashion", "premium_beauty", "storytelling", "product_demo"])
    ingestion.add_argument("--brand", required=True)
    ingestion.add_argument("--title", required=True)
    ingestion.add_argument("--library-dir", type=Path)
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("analysis", type=Path)
    evaluation.add_argument("--expected-dialogue", default="")
    evaluation.add_argument("--scene-id", required=True)
    evaluation.add_argument("--version", required=True)
    evaluation.add_argument("--out", type=Path, required=True)
    comparison = commands.add_parser("compare")
    comparison.add_argument("baseline", type=Path)
    comparison.add_argument("candidate", type=Path)
    comparison.add_argument("--out", type=Path, required=True)
    demos = commands.add_parser("demos")
    demos.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "catalog":
            library = Library()
            result = library.retrieve(args.brief) if args.brief else {
                "references": [r.model_dump() for r in library.references],
                "recipes": [r.model_dump() for r in library.recipes]}
        elif args.command == "analyze":
            result = analyze(args.media, args.out, args.authorized_use,
                             transcript=read_json(args.transcript) if args.transcript else None,
                             whisper_model=args.whisper_model, language=args.language, speech_only=args.speech_only,
                             observations=read_json(args.observations) if args.observations else None)
            result = {"analysis": str(args.out / "analysis.json"), "shots": result["visual"]["shot_count"],
                      "speech_present": result["voice"]["speech_present"]}
        elif args.command == "import":
            root = args.library_dir or get_settings().data_dir / "ad-references"
            result = import_analysis(read_json(args.analysis), args.reference_id, args.category, args.brand,
                                     args.title, root).model_dump()
        elif args.command == "evaluate":
            result = evaluate(read_json(args.analysis), args.expected_dialogue, args.scene_id, args.version)
            media.write_json(args.out, result)
        elif args.command == "compare":
            result = compare(read_json(args.baseline), read_json(args.candidate))
            media.write_json(args.out, result)
        else:
            result = []
            for name, brief in [
                ("ugc_cosmetic_fr", "UGC cosmétique pour un sérum, une présentatrice française, 20 secondes"),
                ("premium_fashion", "Vêtements haut de gamme, un manteau en laine, 20 secondes"),
                ("two_character_story", "Publicité narrative avec deux personnages adultes, un cadeau, 20 secondes"),
            ]:
                proposal = propose(brief, use_llm=False, use_references=True)
                item = {"demo_id": name, "brief": brief, "source": proposal.source,
                        "notes": proposal.notes, "reference_context": proposal.reference_context,
                        "storyboard": proposal.storyboard.model_dump(), "video_generated": False}
                media.write_json(args.out / f"{name}.json", item)
                result.append({"demo": name, "output": str(args.out / f"{name}.json")})
    except (ValueError, OSError, media.MediaError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
