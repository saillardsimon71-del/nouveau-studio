"""Engine catalogue and resolution.

Rules:
  * a requested engine is used only if it reports itself available;
  * otherwise the first available engine of the same kind is used;
  * if none is available and mock is allowed, the simulation engine is used and
    the fallback is *reported* — the job is flagged simulated, never silently.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from .assembly import AssemblyEngine
from .base import Engine, EngineUnavailable
from .comfyui import ComfyUIEngine
from .longcat import LongCatAvatarEngine
from .ltx_native import LTXNativeEngine
from .mock import build_engines as build_mock_engines
from .modal_remote import ModalEngine, ModalH3Engine, FrenchEdgeVoice
from .tts import ChatterboxEngine, VoxCPMEngine

_PREFERENCE: dict[str, list[str]] = {
    "video": ["modal_h3", "modal_ltx", "ltx_native", "comfyui", "mock"],
    "avatar": ["modal_avatar", "longcat_avatar", "mock_avatar"],
    "tts": ["edge_tts_fr", "chatterbox", "voxcpm2", "mock_tts"],
    "image": ["comfyui", "mock_image"],
    "assembly": ["ffmpeg_assembly"],
}

_instances: dict[str, Engine] = {}


def _build() -> dict[str, Engine]:
    global _instances
    if not _instances:
        engines: list[Engine] = [
            ModalH3Engine(),
            ModalEngine("video"),
            ModalEngine("avatar"),
            FrenchEdgeVoice(),
            LTXNativeEngine(),
            ComfyUIEngine(),
            LongCatAvatarEngine(),
            ChatterboxEngine(),
            VoxCPMEngine(),
            AssemblyEngine(),
            *build_mock_engines(),
        ]
        _instances = {e.info.name: e for e in engines}
    return _instances


def get(name: str) -> Engine:
    engines = _build()
    if name not in engines:
        raise KeyError(f"moteur inconnu: {name} (disponibles: {', '.join(sorted(engines))})")
    return engines[name]


def names() -> set[str]:
    return set(_build().keys())


def route_shot(shot, params, requested=None):
    values = {**(shot.get('params') or {}), **params}
    mode = values.get('performance_mode')
    external = values.get('audio_artifact_id') or shot.get('voice_id')
    if values.get('audio_artifact_id') or (external and mode not in ('legacy', 'native')):
        mode = 'voice_first'
    mode = mode or 'legacy'
    talking = bool(shot.get('dialogue', '').strip())
    kind = 'avatar' if talking and (mode == 'voice_first' or shot.get('kind') == 'avatar') else 'video'
    hint = requested or values.get('engine_hint')
    if hint not in names():
        hint = None
    if hint and get(hint).info.kind != kind:
        if requested:
            raise ValueError('Le moteur choisi ne prend pas en charge ce plan audio-conditionné')
        hint = None
    return kind, hint, mode


def engines_of_kind(kind: str) -> list[Engine]:
    return [e for e in _build().values() if e.info.kind == kind]


def resolve(kind: str, requested: str | None = None) -> tuple[Engine, str]:
    """Return (engine, fallback_reason). `fallback_reason` is '' when the request was honoured."""
    settings = get_settings()
    candidates = engines_of_kind(kind)
    if not candidates:
        raise KeyError(f"aucun moteur pour le type {kind}")

    if requested:
        try:
            engine = get(requested)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        if engine.info.simulated and not settings.allow_mock:
            raise EngineUnavailable("La simulation est désactivée sur ce serveur")
        ok, reason = engine.available()
        if ok:
            return engine, ""
        requested_reason = f"{requested} indisponible: {reason}"
    else:
        requested_reason = ""

    for name in _PREFERENCE.get(kind, []):
        if name in _instances and name.startswith("mock"):
            continue
        engine = _instances.get(name)
        if engine is not None:
            ok, _ = engine.available()
            if ok:
                return engine, requested_reason
    for engine in candidates:
        if engine.info.simulated:
            continue
        ok, _ = engine.available()
        if ok:
            return engine, requested_reason

    if settings.allow_mock:
        for engine in candidates:
            if engine.info.simulated:
                reason = requested_reason or "aucun moteur réel disponible dans cet environnement"
                return engine, f"{reason} → simulation"
    raise RuntimeError(f"aucun moteur disponible pour {kind} (simulation désactivée)")


def catalog() -> list[dict[str, Any]]:
    items = []
    for engine in _build().values():
        ok, reason = engine.available()
        if engine.info.simulated and not get_settings().allow_mock:
            ok, reason = False, "Simulation désactivée"
        item = engine.info.to_dict()
        item["available"] = ok
        item["unavailable_reason"] = reason
        items.append(item)
    return items
