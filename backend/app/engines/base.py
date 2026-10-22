"""The only contract between the studio and the outside world.

Adding or replacing a generation engine means writing one class here. Product
logic (projects, shots, jobs, QC, export) never imports an engine directly.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..cost import Usage


class EngineUnavailable(RuntimeError):
    """Raised when the engine cannot run in this environment (no GPU, no weights...)."""


class JobCancelled(RuntimeError):
    pass


class JobContext(Protocol):
    job_id: str
    logs: list[str]

    def log(self, message: str, progress: float | None = None, stage: str = "") -> None: ...
    def check_cancelled(self) -> None: ...


@dataclass
class EngineInfo:
    name: str
    kind: str  # video | avatar | tts | image | assembly
    label: str
    capabilities: list[str] = field(default_factory=list)
    requires_gpu: bool = False
    provider: str = "local"
    gpu: str = "CPU"
    simulated: bool = False   # output is a placeholder, not model output
    verified: bool = False    # this adapter has produced a real result on real hardware
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "label": self.label,
            "capabilities": self.capabilities, "requires_gpu": self.requires_gpu,
            "provider": self.provider, "gpu": self.gpu, "simulated": self.simulated,
            "verified": self.verified, "notes": self.notes,
        }


@dataclass
class EngineRequest:
    kind: str
    output_dir: Path
    project: dict[str, Any] = field(default_factory=dict)
    shot: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)

    @property
    def prompt(self) -> str:
        return str(self.params.get("prompt") or self.shot.get("prompt") or "")

    @property
    def duration_s(self) -> float:
        return float(self.params.get("duration_s") or self.shot.get("duration_s") or 5.0)

    def out(self, filename: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir / filename


@dataclass
class EngineOutput:
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    notes: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def add(self, path: Path, kind: str = "video", mime: str = "video/mp4", **meta: Any) -> None:
        self.artifacts.append(
            {"path": str(path), "kind": kind, "mime": mime, "bytes": path.stat().st_size if path.exists() else 0, "meta": meta}
        )


class Engine(ABC):
    info: EngineInfo

    def available(self) -> tuple[bool, str]:
        return True, ""

    def estimate_seconds(self, request: EngineRequest) -> float:
        return 0.0

    @abstractmethod
    def run(self, request: EngineRequest, ctx: JobContext) -> EngineOutput:
        ...

    # helper for subprocess-based engines
    @staticmethod
    def now() -> float:
        return time.time()
