"""Cost tracking.

The metric that matters is *cost per accepted video*, not cost per GPU-second.
Every job records its own GPU usage and price so the studio can report the real
number later, including the price of failed attempts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import get_settings
from . import db


@dataclass
class Usage:
    provider: str = "local"
    gpu: str = "CPU"
    gpu_seconds: float = 0.0
    rate_usd_hr: float | None = None
    notes: str = ""

    def cost_usd(self) -> float:
        rate = self.rate_usd_hr if self.rate_usd_hr is not None else get_settings().rate_for(self.provider, self.gpu)
        return round(self.gpu_seconds / 3600.0 * rate, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "gpu": self.gpu,
            "gpu_seconds": round(self.gpu_seconds, 2),
            "rate_usd_hr": self.rate_usd_hr if self.rate_usd_hr is not None else get_settings().rate_for(self.provider, self.gpu),
            "cost_usd": self.cost_usd(),
            "notes": self.notes,
        }


def record(project_id: str | None, job_id: str | None, usage: Usage, note: str = "") -> dict[str, Any]:
    return db.insert(
        "cost_events",
        {
            "id": db.new_id("cost"),
            "project_id": project_id,
            "job_id": job_id,
            "provider": usage.provider,
            "gpu": usage.gpu,
            "gpu_seconds": usage.gpu_seconds,
            "rate_usd_hr": usage.rate_usd_hr
            if usage.rate_usd_hr is not None
            else get_settings().rate_for(usage.provider, usage.gpu),
            "usd": usage.cost_usd(),
            "note": note or usage.notes,
            "created_at": db.now_iso(),
        },
    )


def project_summary(project_id: str) -> dict[str, Any]:
    events = db.find("cost_events", "project_id = ?", (project_id,), order="created_at ASC")
    jobs = db.find("jobs", "project_id = ?", (project_id,), order="created_at ASC")
    total = round(sum(e["usd"] for e in events), 4)
    gpu_s = round(sum(e["gpu_seconds"] for e in events), 1)
    succeeded = [j for j in jobs if j["status"] == "succeeded"]
    failed = [j for j in jobs if j["status"] == "failed"]
    exports = db.find("exports", "project_id = ?", (project_id,))
    accepted_cost = round(total / len(exports), 4) if exports else None
    return {
        "project_id": project_id,
        "cost_usd": total,
        "gpu_seconds": gpu_s,
        "jobs": len(jobs),
        "jobs_succeeded": len(succeeded),
        "jobs_failed": len(failed),
        "attempts_per_success": round(len(jobs) / len(succeeded), 2) if succeeded else None,
        "exports": len(exports),
        "cost_per_export_usd": accepted_cost,
        "by_engine": _group(events, "provider"),
        "events": events[-50:],
    }


def _group(events: list[dict[str, Any]], key: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in events:
        out[e[key]] = round(out.get(e[key], 0.0) + e["usd"], 4)
    return out
