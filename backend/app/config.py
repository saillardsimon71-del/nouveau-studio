"""Runtime configuration.

Everything is env-driven with sane defaults so the studio runs locally with zero
setup. GPU engines are configured but *not* required: the studio boots, the UI
works, and jobs run against whichever engines are actually reachable.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_flag(name: str, default: bool) -> bool:
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    repo_root: Path = field(default_factory=_repo_root)

    # Storage. `data/` holds every generated artifact and is git-ignored.
    data_dir: Path = field(init=False)
    db_path: Path = field(init=False)
    static_dir: Path = field(init=False)

    # HTTP
    host: str = field(default_factory=lambda: _env("PVS_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("PVS_PORT", "8000")))

    # Job execution
    max_workers: int = field(default_factory=lambda: int(_env("PVS_MAX_WORKERS", "1")))
    requeue_on_boot: bool = field(default_factory=lambda: _env_flag("PVS_REQUEUE_ON_BOOT", True))
    default_provider: str = field(default_factory=lambda: _env("PVS_PROVIDER", "local"))

    # Engine availability -----------------------------------------------------------------
    # Local dev default: the `mock` engine is used when a real engine is not
    # configured. Mock output is explicitly labelled and never sold as AI video.
    allow_mock: bool = field(default_factory=lambda: _env_flag("PVS_ALLOW_MOCK", True))

    # LTX (native pipelines, runs on a GPU host)
    ltx_python: str = field(default_factory=lambda: _env("PVS_LTX_PYTHON", "python"))
    ltx_repo: Path = field(init=False)
    ltx_models: Path = field(init=False)
    ltx_default_pipeline: str = field(default_factory=lambda: _env("PVS_LTX_PIPELINE", "dfr"))

    # Talking head (LongCat-Video-Avatar / InfiniteTalk, GPU host)
    avatar_python: str = field(default_factory=lambda: _env("PVS_AVATAR_PYTHON", "python"))
    avatar_repo: Path = field(init=False)
    avatar_weights: Path = field(init=False)
    avatar_default: str = field(default_factory=lambda: _env("PVS_AVATAR_ENGINE", "longcat"))

    # TTS (Chatterbox / VoxCPM2, GPU host or local CPU)
    tts_python: str = field(default_factory=lambda: _env("PVS_TTS_PYTHON", "python"))

    # ComfyUI (optional execution backend)
    comfy_url: str = field(default_factory=lambda: _env("PVS_COMFY_URL", "").rstrip("/"))

    # Director (LLM). Any OpenAI-compatible endpoint: DeepSeek, OpenAI, vLLM, Ollama.
    llm_base_url: str = field(default_factory=lambda: _env("PVS_LLM_BASE_URL", "https://api.deepseek.com/v1"))
    llm_model: str = field(default_factory=lambda: _env("PVS_LLM_MODEL", "deepseek-chat"))
    llm_api_key: str = field(default_factory=lambda: _env("PVS_LLM_API_KEY", ""))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("PVS_LLM_TIMEOUT", "120")))

    # Cost model (USD per GPU-hour). Indicative public list prices, Oct 2026 —
    # override per provider with PVS_RATE_<PROVIDER>_<GPU> or edit RATE_CARD.
    rate_card: dict[str, float] = field(
        default_factory=lambda: {
            "runpod:RTX_4090": 0.69,
            "runpod:RTX_5090": 0.99,
            "runpod:A100_80GB": 1.39,
            "runpod:H100_80GB": 2.89,
            "modal:H100_80GB": 3.95,
            "modal:A100_80GB": 2.50,
            "local:local": 0.0,
            "local:CPU": 0.0,
        }
    )

    def __post_init__(self) -> None:
        self.data_dir = Path(_env("PVS_DATA_DIR", str(self.repo_root / "data"))).resolve()
        self.db_path = self.data_dir / "studio.db"
        self.static_dir = self.repo_root / "frontend" / "dist"
        self.ltx_repo = Path(_env("PVS_LTX_REPO", "/opt/LTX-2")).expanduser()
        self.ltx_models = Path(_env("PVS_LTX_MODELS", "/models/ltx-2.5")).expanduser()
        self.avatar_repo = Path(_env("PVS_AVATAR_REPO", "/opt/LongCat-Video")).expanduser()
        self.avatar_weights = Path(_env("PVS_AVATAR_WEIGHTS", "/models/LongCat-Video-Avatar-1.5")).expanduser()
        for sub in ("projects", "uploads", "exports", "tmp", "voices", "characters"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)

    # ffmpeg -------------------------------------------------------------------------------
    @property
    def ffmpeg(self) -> str:
        explicit = _env("PVS_FFMPEG")
        if explicit:
            return explicit
        bundled = self.repo_root / ".tools" / "ff" / "bin" / "ffmpeg"
        if bundled.exists():
            return str(bundled)
        found = shutil.which("ffmpeg")
        if found:
            return found
        try:  # imageio-ffmpeg ships a static build; keeps the studio usable anywhere
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # pragma: no cover - no ffmpeg at all
            return "ffmpeg"

    def rate_for(self, provider: str, gpu: str) -> float:
        env_key = f"PVS_RATE_{provider.upper()}_{gpu.upper()}"
        if _env(env_key):
            return float(_env(env_key))
        return self.rate_card.get(f"{provider}:{gpu}", 0.0)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
