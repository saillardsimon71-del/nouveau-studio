#!/usr/bin/env python3
"""Licensed advertising corpus ingestion, real CPU analysis, and honest prompt A/B.

Only downloads exact manually-curated Wikimedia Commons video titles; verifies
canonical Creative Commons license URL from live Wikimedia metadata. Never
downloads from a brand site or from YouTube, never trains video-model weights.
Uses existing Studio ad_references.analyze and import_analysis functions.
Original media are ephemeral; SHA-256, credits, observed media metrics persist.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
from app.ad_references.analysis import analyze
from app.ad_references.library import Library, import_analysis
from app.ad_references.performance import enrich_storyboard, local_storyboard

MANIFEST = REPO / "studio/ad-references/research/licensed-commons-corpus.json"
LIBRARY = REPO / "studio/ad-references"
DATA = REPO / "artifacts/ad-licensed-research"
API = "https://commons.wikimedia.org/w/api.php"
UA = "SiteQuiVend-AdResearch/0.1 (https://sitequivend.fr; nonprofit internal ad analysis; commons licensed media)"
ALLOWED = {"creativecommons.org"}
MAX_DOWNLOAD = 40 * 1024 * 1024


def retrieve_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(request, timeout=50) as response:
        return json.load(response)


def image_info(filename: str) -> dict:
    params = urlencode({
        "action": "query", "format": "json", "formatversion": "2",
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "titles": "File:" + filename,
    })
    data = retrieve_json(API + "?" + params)
    pages = data.get("query", {}).get("pages", [])
    if len(pages) != 1 or "imageinfo" not in pages[0]:
        raise ValueError("Wikimedia Commons file metadata unavailable: " + filename)
    return pages[0]["imageinfo"][0]


def normalized_license_url(url: str) -> str:
    parsed = urlparse(html.unescape(url.strip()))
    if parsed.hostname not in ALLOWED or parsed.scheme not in ("http", "https"):
        raise ValueError("License metadata does not point to a Creative Commons license")
    return f"{parsed.hostname}{parsed.path.rstrip('/')}".lower()


def verify_license(item: dict, meta: dict) -> None:
    value = meta.get("extmetadata", {}).get("LicenseUrl", {}).get("value", "")
    if normalized_license_url(value) != normalized_license_url(item["license_url"]):
        raise ValueError(
            f"{item['id']}: expected {item['license_url']}, got {value!r}; refusing media download"
        )
    mime = meta.get("mime", "")
    if not (mime.startswith("video/") or mime in ("application/ogg",)):
        raise ValueError(item["id"] + ": Commons media is not a video")
    size = int(meta.get("size", 0))
    if not 30_000 < size <= MAX_DOWNLOAD:
        raise ValueError(item["id"] + ": media outside 30KB..40MiB")
    raw_url = meta.get("url", "")
    p = urlparse(raw_url)
    if p.scheme != "https" or p.hostname not in ("upload.wikimedia.org",):
        raise ValueError(item["id"] + ": unexpected media host")
    if "ND" in item["license"] or "NC" in item["license"]:
        raise ValueError("Noncommercial/no-derivatives media excluded")


def download(item: dict, url: str, size: int) -> Path:
    suffix = Path(item["filename"]).suffix.lower()
    out = DATA / "media" / (item["id"] + suffix)
    out.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": UA})
    transferred = 0
    with urlopen(request, timeout=120) as response, out.open("wb") as dest:
        # Final URL must remain within Wikimedia storage (including redirects).
        if urlparse(response.url).hostname != "upload.wikimedia.org":
            raise ValueError("Unexpected redirect to a non-Wikimedia media host")
        while block := response.read(1024 * 1024):
            transferred += len(block)
            if transferred > MAX_DOWNLOAD:
                raise ValueError("Media download exceeds 40MiB cap")
            dest.write(block)
    if transferred != size:
        out.unlink(missing_ok=True)
        raise ValueError(f"Media size mismatch ({transferred} != {size})")
    return out


def asr_checkpoint() -> Path | None:
    if os.environ.get("PVS_CORPUS_ASR", "1") != "1":
        return None
    from pathlib import Path
    import whisper
    cache = DATA / "models"
    cache.mkdir(parents=True, exist_ok=True)
    checkpoint = cache / "tiny.pt"
    if not checkpoint.is_file():
        print("Downloading Whisper tiny weights for CPU analysis only (one-time runner cache)", flush=True)
        whisper.load_model("tiny", device="cpu", download_root=str(cache))
    if not checkpoint.is_file():
        raise RuntimeError("Whisper tiny CPU checkpoint was not obtained")
    return checkpoint


def ingest(item: dict, checkpoint: Path | None) -> dict:
    info = image_info(item["filename"])
    verify_license(item, info)
    media = download(item, info["url"], int(info["size"]))
    use_asr = checkpoint is not None and item.get("asr", False)
    try:
        result = analyze(media, DATA / "analysis" / item["id"],
                         authorization=f"Commons {item['license']} | {item['page']} | {item['author']}",
                         whisper_model=checkpoint if use_asr else None,
                         language=item["language"])
    except Exception:
        media.unlink(missing_ok=True)
        raise
    # Never let a music hallucination or tiny token sample become a Director pace rule.\n    voice = result["voice"]\n    if (voice.get("transcription_source") == "whisper_local_cpu" and\n        (int(voice.get("word_count") or 0) < 8 or\n         float(voice.get("speech_span_s") or 0) < 2.0)):\n        voice["words_per_minute_speech_span"] = None\n        voice["speech_present"] = None\n        voice["transcription_source"] = "whisper_local_cpu_insufficient_evidence"\n        voice.setdefault("limitations", []).append("Too few speech words for a defensible delivery-rate estimate.")\n        (DATA / "analysis" / item["id"] / "analysis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")\n    recorded = import_analysis(result, item["id"], item["category"],
                               item["brand"], item["title"], LIBRARY)
    path = LIBRARY / "catalog" / (item["id"] + ".json")
    data = recorded.model_dump()
    # The media file is ephemeral and must never be described as local after CI.
    data["source"].update({
        "url": item["page"],
        "license": item["license"],
        "rights_note": f"{item['license']} — {item['author']}, attribution required; no endorsement. Rights in people, brands and soundtrack not independently cleared.",
        "local_path": None,
        "downloaded": False,
        "authorization_evidence": f"Commons metadata verified: {item['license_url']}; {item['page']}",
    })
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Avoid committing transient images and source media to the repository.
    media.unlink(missing_ok=True)
    visual = result["visual"]
    voice = result["voice"]
    entry = {
        "reference_id": item["id"], "source": item["page"],
        "license": item["license"], "author": item["author"],
        "license_review_status": item["review"],
        "file_sha256": result["source"]["sha256"],
        "duration_seconds": result["duration_seconds"],
        "shot_cut_candidates": visual["shot_count"],
        "speech_asr_executed": bool(use_asr and voice.get("transcription_source") == "whisper_local_cpu"),
        "measured_wpm": voice.get("words_per_minute_speech_span"),
        "limitations": result["limitations"],
    }
    print("ANALYZED " + item["id"] + " " + json.dumps({k: entry[k] for k in
        ("duration_seconds", "shot_cut_candidates", "speech_asr_executed", "measured_wpm")}), flush=True)
    return entry


def baseline_vs_reference() -> list[dict]:
    """Same four-shot baseline for A and B: B only adds licensed-reference rules."""
    results = []
    lib = Library()
    briefs = [
        ("ugc_fr", "UGC cosmétique française, présentatrice face caméra, 20 secondes", "ugc_presenter"),
        ("fashion", "Mode luxe, collection de vêtements, 20 secondes", "premium_fashion"),
    ]
    for label, brief, cat in briefs:
        original = local_storyboard(brief, 20, cat)
        context = lib.retrieve(brief, cat)
        if not context:
            raise ValueError("No reference context for "+cat)
        candidate = enrich_storyboard(copy.deepcopy(original), context)
        a, b = original.model_dump(), candidate.model_dump()
        assert len(a["shots"]) == len(b["shots"]) == 4
        assert all(x["dialogue"] == y["dialogue"] and x["duration_s"] == y["duration_s"]
                   for x, y in zip(a["shots"], b["shots"]))
        report = {
            "brief": brief, "category": cat,
            "same_base_storyboard_and_dialogue": True,
            "A_no_reference": a, "B_with_references": b,
            "B_references": context,
            "videos_generated": False,
            "claim": "Prompt differences only; no claim of improved video, acting or conversion.",
        }
        out = DATA / "ab-prompts" / (label + "-same-brief.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        results.append({"brief": label, "A_B_file": str(out.relative_to(REPO)),
                        "B_source_count": len(context.get("references", [])),
                        "observed_wpm": context.get("measured_pace_wpm")})
    return results


def validate_only():
    content = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = content["items"]
    assert len(items) == 8
    assert len({x["id"] for x in items}) == len(items)
    for item in items:
        assert item["id"].startswith("licensed_")
        assert item["page"].startswith("https://commons.wikimedia.org/wiki/File:")
        assert item["license"].startswith("CC BY")
        assert item["license_url"].startswith("https://creativecommons.org/licenses/")
        assert item["category"] in ("ugc_presenter","premium_beauty","premium_fashion","storytelling","product_demo")
    print("STATIC VALIDATION OK (8 curated citations, no network, no GPU)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("check", "ingest", "ab"))
    args = p.parse_args()
    if args.mode == "check":
        validate_only()
        return
    if args.mode == "ab":
        print(json.dumps(baseline_vs_reference(), indent=2, ensure_ascii=False))
        return
    validate_only()
    checkpoint = asr_checkpoint()
    summary, failures = [], []
    for item in json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]:
        try:
            summary.append(ingest(item, checkpoint))
        except Exception as exc:
            failures.append({"reference_id": item["id"], "error": type(exc).__name__ + ": " + str(exc)[:350]})
            print("FAILED " + item["id"] + " " + str(exc), flush=True)
        time.sleep(1)
    report = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "total_candidates": 8, "analyzed_count": len(summary),
        "asr_count": sum(x["speech_asr_executed"] for x in summary),
        "analyses": summary, "failures": failures,
        "warning": "Only real downloaded files counted. Speech absent/unknown without ASR. No video-quality claims.",
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "ingestion-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                                encoding="utf-8")
    if len(summary) < 5:
        raise RuntimeError(f"Insufficient verified real media analyses: {len(summary)}/8; see report")
    print(json.dumps(baseline_vs_reference(), indent=2, ensure_ascii=False))
    print("CORPUS INGESTION DONE: " + str(len(summary)) + " authorized real ad videos", flush=True)


if __name__ == "__main__":
    main()
