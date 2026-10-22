#!/usr/bin/env python3
"""Benchmark runner for the three reference tests.

Two modes:

  --dry-run   validate the scenario, print the exact commands and cost estimate,
              write nothing to the GPU. Works anywhere.
  (default)   submit each variant to the studio API, wait, run automatic QC and
              write a result record. Requires a reachable studio with real
              engines configured — otherwise the run is refused, because a
              benchmark that silently measures the simulation engine is worse
              than no benchmark.

Usage:
    python benchmarks/run_benchmark.py --scenario test_a_avatar --dry-run
    python benchmarks/run_benchmark.py --scenario test_b_cinematic --api http://gpu-host:8000
    python benchmarks/run_benchmark.py --all --dry-run --json benchmarks/results/plan.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "benchmarks" / "scenarios"
RESULTS = ROOT / "benchmarks" / "results"

# Indicative public prices, USD/GPU-hour (Oct 2026). Override with --rates.
DEFAULT_RATES = {
    "runpod:A100_80GB": 1.39,
    "runpod:H100_80GB": 2.89,
    "runpod:RTX_4090": 0.69,
    "runpod:RTX_5090": 0.99,
    "modal:H100_80GB": 3.95,
    "local:CPU": 0.0,
}


def load(scenario_id: str) -> dict[str, Any]:
    path = SCENARIOS / f"{scenario_id}.yaml"
    if not path.exists():
        raise SystemExit(f"scénario introuvable: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def estimate_cost(variant: dict[str, Any], duration_s: float, rates: dict[str, float]) -> dict[str, Any]:
    """Rough GPU-second estimate, deliberately conservative and clearly labelled."""
    engine = variant["engine"]
    gpu = variant.get("gpu", "A100_80GB")
    # seconds of GPU per second of generated video, from published speed claims:
    # LTX-2.5 DFR ≈ 90-150 s/clip of 5 s on H100; distilled ≈ 20-40 s;
    # LongCat 720p ≈ 40-80 s per 8 s clip on A100; Wan TI2V-5B ≈ 10-20 s.
    multiplier = {
        ("ltx_native", "dfr"): 25.0,
        ("ltx_native", "distilled"): 7.0,
        ("ltx_native", "two_stages"): 18.0,
        ("longcat_avatar", None): 8.0,
        ("infinite_talk", None): 12.0,
        ("wan22_ti2v", None): 3.0,
        ("comfyui", None): 10.0,
    }
    key = (engine, (variant.get("params") or {}).get("pipeline"))
    gpu_seconds = duration_s * multiplier.get(key, multiplier.get((engine, None), 10.0))
    rate = rates.get(f"runpod:{gpu}") or rates.get("runpod:A100_80GB", 1.39)
    return {
        "gpu": gpu,
        "gpu_seconds_estimate": round(gpu_seconds, 1),
        "rate_usd_hr": rate,
        "cost_usd_estimate": round(gpu_seconds / 3600 * rate, 3),
        "assumption": "GPU-seconds per video-second from published speed claims; verify on first real run",
    }


def dry_run(scenario: dict[str, Any], rates: dict[str, float]) -> dict[str, Any]:
    variants = []
    for variant in scenario.get("variants", []):
        variants.append(
            {
                "engine": variant["engine"],
                "label": variant["label"],
                "params": variant.get("params", {}),
                **estimate_cost(variant, float(scenario.get("duration_s", 5)), rates),
            }
        )
    return {
        "scenario": scenario["id"],
        "title": scenario["title"],
        "duration_s": scenario.get("duration_s"),
        "status": "planned_not_executed",
        "variants": variants,
        "criteria": scenario.get("criteria", []),
        "note": "Aucune génération n'a été lancée: ce fichier est un plan, pas un résultat.",
    }


def live_run(scenario: dict[str, Any], api: str, rates: dict[str, float], timeout: int) -> dict[str, Any]:
    client = httpx.Client(base_url=api, timeout=60)
    system = client.get("/api/system").json()
    real_video = [
        e for e in system["engines"]
        if e["available"] and not e["simulated"] and e["kind"] in {"video", "avatar"}
    ]
    if not real_video:
        raise SystemExit(
            "Aucun moteur réel disponible côté studio. Refus d'exécuter un benchmark qui "
            "mesurerait la simulation. Configurer LTX-2.5 / LongCat puis relancer."
        )

    project = client.post("/api/projects", json={
        "name": f"benchmark {scenario['id']}",
        "brief": scenario.get("goal", scenario.get("title", "")),
        "format": scenario.get("format", "9:16"),
    }).json()

    board = {
        "concept": scenario.get("title", ""),
        "script": scenario.get("spoken_text", ""),
        "style_guide": "",
        "shots": [],
    }
    if scenario["id"] == "test_c_identity":
        for shot in scenario["shots"]:
            board["shots"].append({
                "kind": shot["kind"],
                "title": shot["id"],
                "duration_s": scenario.get("duration_s", 4),
                "dialogue": shot.get("dialogue", ""),
                "prompt": scenario["shared_appearance_prompt"] + " " + shot.get("prompt", ""),
                "camera": "", "transition": "cut", "engine_hint": "", "notes": "",
            })
    else:
        board["shots"].append({
            "kind": "avatar" if scenario["id"] == "test_a_avatar" else "b_roll",
            "title": scenario["title"],
            "duration_s": scenario.get("duration_s", 5),
            "dialogue": scenario.get("spoken_text", ""),
            "prompt": scenario.get("engine_prompt") or scenario.get("prompt", ""),
            "camera": "", "transition": "cut", "engine_hint": "", "notes": "",
        })
    project = client.post(f"/api/projects/{project['id']}/storyboard", json=board).json()
    shot = project["shots"][0]

    results = []
    for variant in scenario.get("variants", []):
        started = time.time()
        job = client.post(
            f"/api/shots/{shot['id']}/generate",
            json={"engine": variant["engine"], "params": variant.get("params", {})},
        )
        job = job.json() if job.headers.get("content-type", "").startswith("application/json") else {}
        job_id = job.get("id")
        if not job_id:
            results.append({"engine": variant["engine"], "status": "rejected_by_api",
                            "detail": "moteur non résolu par le studio"})
            continue
        deadline = started + timeout
        final: dict[str, Any] = {}
        while time.time() < deadline:
            final = client.get(f"/api/jobs/{job_id}").json()
            if final["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(3)
        results.append({
            "engine": variant["engine"],
            "label": variant["label"],
            "params": variant.get("params", {}),
            "status": final.get("status", "timeout"),
            "simulated": bool(final.get("simulated")),
            "gpu_seconds": final.get("gpu_seconds"),
            "cost_usd": final.get("cost_usd"),
            "job_id": job_id,
            "error": final.get("error"),
            "wall_s": round(time.time() - started, 1),
            **estimate_cost(variant, float(scenario.get("duration_s", 5)), rates),
        })
    return {
        "scenario": scenario["id"],
        "title": scenario["title"],
        "status": "executed",
        "api": api,
        "project_id": project["id"],
        "variants": results,
        "criteria": scenario.get("criteria", []),
        "review": "Les scores visuels (criteria) sont renseignés à la main après visionnage.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--json", default=None, help="chemin du résultat à écrire")
    args = parser.parse_args()

    if not args.scenario and not args.all:
        parser.error("--scenario ou --all")

    ids = [p.stem for p in sorted(SCENARIOS.glob("*.yaml"))] if args.all else [args.scenario]
    rates = DEFAULT_RATES
    output: list[dict[str, Any]] = []
    for scenario_id in ids:
        scenario = load(scenario_id)
        result = dry_run(scenario, rates) if args.dry_run else live_run(scenario, args.api, rates, args.timeout)
        output.append(result)
        print(f"== {scenario_id}: {result['status']}")
        for variant in result["variants"]:
            print(
                f"   - {variant['engine']:16} {variant.get('gpu', ''):11} "
                f"~{variant.get('gpu_seconds_estimate', '?')}s GPU  "
                f"~{variant.get('cost_usd_estimate', '?')} $"
            )

    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": "dry_run" if args.dry_run else "live",
            "results": output,
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"écrit {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
