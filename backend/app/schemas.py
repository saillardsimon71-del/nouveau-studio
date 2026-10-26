"""API schemas (pydantic v2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ShotKind = Literal["avatar", "b_roll", "screen_capture", "title", "product"]
Transition = Literal["cut", "fade", "dissolve", "slide"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brief: str = ""
    format: Literal["9:16", "16:9", "1:1"] = "9:16"


class ProjectUpdate(BaseModel):
    name: str | None = None
    brief: str | None = None
    format: Literal["9:16", "16:9", "1:1"] | None = None
    concept: str | None = None
    script: str | None = None
    style_guide: str | None = None
    music_path: str | None = None
    status: str | None = None
    settings: dict[str, Any] | None = None


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    appearance: dict[str, Any] = Field(default_factory=dict)
    voice_id: str | None = None
    project_id: str | None = None
    base_image: str | None = None
    refs: list[str] = Field(default_factory=list)


class VoiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    engine: str = "chatterbox"
    language: str = "fr"
    ref_audio: str | None = None
    transcript: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class ShotPatch(BaseModel):
    kind: ShotKind | None = None
    title: str | None = None
    duration_s: float | None = Field(default=None, gt=0, le=120)
    dialogue: str | None = None
    prompt: str | None = None
    camera: str | None = None
    character_id: str | None = None
    voice_id: str | None = None
    transition: Transition | None = None
    params: dict[str, Any] | None = None
    selected_artifact: str | None = None
    status: str | None = None

    @field_validator("duration_s")
    @classmethod
    def _round_duration(cls, v: float | None) -> float | None:
        return None if v is None else round(v, 2)


class ShotCreate(BaseModel):
    kind: ShotKind = "b_roll"
    title: str = ""
    duration_s: float = 5.0
    dialogue: str = ""
    prompt: str = ""
    camera: str = ""
    character_id: str | None = None
    transition: Transition = "cut"


class ShotSpec(BaseModel):
    """One plan in a storyboard proposal."""

    kind: ShotKind = "b_roll"
    title: str = ""
    duration_s: float = Field(default=5.0, gt=0, le=60)
    dialogue: str = ""
    prompt: str = ""
    camera: str = ""
    transition: Transition = "cut"
    engine_hint: str = ""
    notes: str = ""
    performance: dict[str, Any] = Field(default_factory=dict)
    creative_provenance: list[dict[str, Any]] = Field(default_factory=list)
    character_id: str | None = None


class Storyboard(BaseModel):
    concept: str = ""
    script: str = ""
    style_guide: str = ""
    shots: list[ShotSpec] = Field(default_factory=list)

    @field_validator("shots")
    @classmethod
    def _non_empty(cls, v: list[ShotSpec]) -> list[ShotSpec]:
        if not v:
            raise ValueError("a storyboard needs at least one shot")
        return v


class StoryboardRequest(BaseModel):
    brief: str = ""
    target_duration_s: float | None = None
    character_id: str | None = None
    extra_instructions: str = ""
    use_llm: bool | None = None  # None = auto (use LLM when a key is configured)
    use_references: bool = False
    ad_category: Literal["ugc_presenter", "premium_beauty", "premium_fashion", "storytelling", "product_demo"] | None = None


class GenerateRequest(BaseModel):
    engine: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    music_path: str | None = None
    music_gain_db: float = -20.0
    music_ducking: bool = False  # opt-in; requires a music bed and voiced clip audio
    subtitles: bool = True
    transitions: bool = True
    loudness_target: float = -14.0
    title_card: bool = False
    format: Literal["9:16", "16:9", "1:1"] = "9:16"
    fps: int = 30


class RetakeRequest(BaseModel):
    """Targeted regeneration of a time region inside an existing clip."""

    artifact_id: str
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    prompt: str = ""
    seed: int | None = None

    @field_validator("end_s")
    @classmethod
    def _check(cls, v: float, info) -> float:
        start = info.data.get("start_s", 0)
        if v <= start:
            raise ValueError("end_s must be greater than start_s")
        return v
