from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import NotRequired, TypedDict

Category = Literal["ugc_presenter", "premium_beauty", "premium_fashion", "storytelling", "product_demo"]
Basis = Literal["source_description", "video_observation", "acoustic_measurement", "model_inference"]


class Evidence(BaseModel):
    url: str = ""
    locator: str
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, ge=0)
    media_sha256: str | None = None


class Observation(BaseModel):
    id: str
    domain: Literal["visual", "voice", "marketing", "narrative"]
    value: Any
    basis: Basis
    confidence: float = Field(ge=0, le=1)
    evidence: Evidence
    uncertainty: str = ""

    @model_validator(mode="after")
    def check_evidence(self):
        start, end = self.evidence.start_s, self.evidence.end_s
        if self.basis != "source_description" and (start is None or end is None):
            raise ValueError("media observations require start/end timestamp evidence")
        if start is not None and end is not None and end < start:
            raise ValueError("end timestamp before start")
        return self


class Source(BaseModel):
    url: str
    origin_url: str | None = None
    license: str
    rights_note: str
    analysis_access: Literal["metadata_only", "sampled_frames", "full_video"]
    media_authorized: bool = False
    authorization_evidence: str = ""
    verification_date: str
    downloaded: bool = False
    local_path: str | None = None

    @model_validator(mode="after")
    def check_authorization(self):
        if self.media_authorized and not self.authorization_evidence.strip():
            raise ValueError("authorized media require authorization evidence")
        return self


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    reference_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    category: Category
    brand: str
    title: str
    source: Source
    publication_date: str | None = None
    publication_date_basis: str = "unknown"
    duration_seconds: float | None = Field(default=None, gt=0)
    duration_basis: str = "unknown"
    platform: str
    format: str | None = None
    ad_type: str
    concept: str
    hook: dict[str, Any] = Field(default_factory=dict)
    narrative: dict[str, Any] = Field(default_factory=dict)
    commercial_message: str
    editing_style: str | None = None
    dialogue_present: bool | None = None
    voice: dict[str, Any] = Field(default_factory=dict)
    observations: list[Observation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_access(self):
        if self.source.analysis_access == "metadata_only":
            if self.voice or any(o.basis != "source_description" for o in self.observations):
                raise ValueError("metadata_only cannot contain measured voice or video observations")
        return self


class RecipeRule(TypedDict):
    instruction: str
    reference_id: str
    observation_id: str
    adaptation: NotRequired[str]


class Recipe(BaseModel):
    recipe_id: str
    category: Category
    title: str
    basis: Literal["source_description", "analyzed_media"]
    reference_ids: list[str] = Field(min_length=1)
    rules: list[RecipeRule] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("rules")
    @classmethod
    def validate_rules(cls, rules):
        for rule in rules:
            if any(not isinstance(rule.get(key), str) or not rule[key].strip()
                   for key in ("instruction", "reference_id", "observation_id")):
                raise ValueError("recipe rules require instruction, reference_id and observation_id")
        return rules
