"""Schémas de la Phase 3 : profils, analyses, candidats, coûts, réglages API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import CRITERIA, MAX_CLIP_SECONDS, MIN_CLIP_SECONDS


def _strip(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    editorial_focus: str | None = Field(default=None, max_length=2000)
    threshold: float = Field(default=60.0, ge=0, le=100)
    weights: dict[str, float]
    output_language: str = Field(default="fr", min_length=2, max_length=10)
    min_duration: float = Field(default=MIN_CLIP_SECONDS, ge=MIN_CLIP_SECONDS, le=MAX_CLIP_SECONDS)
    max_duration: float = Field(default=MAX_CLIP_SECONDS, ge=MIN_CLIP_SECONDS, le=MAX_CLIP_SECONDS)
    max_candidates: int = Field(default=12, ge=1, le=50)
    use_vision: bool = True
    is_default: bool = False
    # --- Montage (Phase 4)
    subtitle_mode: Literal["source", "translate", "off"] = "source"
    subtitle_style: dict[str, Any] = Field(default_factory=dict)
    layout: Literal["focus", "blur", "fill"] = "focus"
    jump_zoom: bool = True
    zoom_intensity: float = Field(default=0.12, ge=0, le=0.5)
    hook_enabled: bool = True
    cta_enabled: bool = True
    cta_text: str | None = Field(default=None, max_length=200)
    render_encoder: Literal["libx264", "h264_nvenc"] = "libx264"
    # --- Audio et facecam (Phase 5). Niveaux en dB, appliqués avant la normalisation finale.
    narration_mode: Literal["auto", "off"] = "auto"
    narration_voice: str = Field(default="fr_FR-siwis-medium", max_length=60)
    narration_speed: float = Field(default=1.0, ge=0.7, le=1.4)
    narration_level_db: float = Field(default=0.0, ge=-20, le=10)
    game_level_db: float = Field(default=0.0, ge=-30, le=10)
    music_mode: Literal["suggest", "library", "off"] = "suggest"
    music_level_db: float = Field(default=-18.0, ge=-40, le=0)
    source_music_mode: Literal["attenuate", "detect", "off"] = "attenuate"
    source_music_reduction_db: float = Field(default=15.0, ge=3, le=40)
    facecam_mode: Literal["crop", "off"] = "crop"
    censor_profanity: bool = True
    bleep_profanity: bool = True
    narration_title: bool = True
    react_overlay: bool = True
    min_confidence: float = Field(default=0.5, ge=0, le=1)
    # --- Transitions et effets ponctuels (Phase 7)
    effects_mode: Literal["auto", "off"] = "auto"
    transition_in: Literal["none", "fade", "zoom"] = "zoom"
    transition_out: Literal["none", "fade"] = "fade"
    sfx_mode: Literal["auto", "off"] = "auto"
    sfx_level_db: float = Field(default=-14.0, ge=-40, le=0)

    @field_validator("narration_voice")
    @classmethod
    def _voice(cls, value: str) -> str:
        from app.models_registry import PIPER_VOICES

        if value not in PIPER_VOICES:
            raise ValueError(f"Voix inconnue. Voix disponibles : {', '.join(PIPER_VOICES)}")
        return value

    @field_validator("subtitle_style")
    @classmethod
    def _style(cls, value: dict[str, Any]) -> dict[str, Any]:
        from app.render.style import normalize_subtitle_style

        return normalize_subtitle_style(value)

    @field_validator("cta_text")
    @classmethod
    def _cta(cls, value: str | None) -> str | None:
        return _strip(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le nom du profil ne peut pas être vide")
        return value

    @field_validator("description", "editorial_focus")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return _strip(value)

    @field_validator("weights")
    @classmethod
    def _weights(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = set(value) - set(CRITERIA)
        if unknown:
            raise ValueError(f"Critères inconnus : {', '.join(sorted(unknown))}")
        full = {key: float(value.get(key, 1.0)) for key in CRITERIA}
        if any(w < 0 or w > 5 for w in full.values()):
            raise ValueError("Chaque pondération doit être comprise entre 0 et 5")
        if sum(full.values()) <= 0:
            raise ValueError("Au moins un critère doit avoir une pondération positive")
        return full

    @model_validator(mode="after")
    def _durations(self) -> ProfileIn:
        if self.min_duration > self.max_duration:
            raise ValueError("La durée minimale dépasse la durée maximale")
        return self


class ProfileOut(BaseModel):
    id: str
    name: str
    description: str | None
    editorial_focus: str | None
    threshold: float
    weights: dict[str, float]
    output_language: str
    min_duration: float
    max_duration: float
    max_candidates: int
    use_vision: bool
    is_default: bool
    subtitle_mode: str
    subtitle_style: dict[str, Any]
    layout: str
    jump_zoom: bool
    zoom_intensity: float
    hook_enabled: bool
    cta_enabled: bool
    cta_text: str | None
    render_encoder: str
    narration_mode: str
    narration_voice: str
    narration_speed: float
    narration_level_db: float
    game_level_db: float
    music_mode: str
    music_level_db: float
    source_music_mode: str
    source_music_reduction_db: float
    facecam_mode: str
    censor_profanity: bool
    bleep_profanity: bool
    narration_title: bool
    react_overlay: bool
    min_confidence: float
    effects_mode: str
    transition_in: str
    transition_out: str
    sfx_mode: str
    sfx_level_db: float
    created_at: datetime
    updated_at: datetime


class CriterionOut(BaseModel):
    key: str
    label: str


class ClipScoreOut(BaseModel):
    criterion: str
    label: str
    score: float
    justification: str | None


class FrameOut(BaseModel):
    t: float
    url: str


class CandidateOut(BaseModel):
    id: str
    position: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    peak_seconds: float | None
    signal_score: float
    status: str
    summary: str | None
    reason: str | None
    events: list[dict[str, object]]
    warnings: list[str]
    confidence: float | None
    overall_score: float | None
    selected: bool
    rejection_reason: str | None
    error_message: str | None
    transcript_excerpt: str | None
    scores: list[ClipScoreOut]
    frames: list[FrameOut]
    signals: dict[str, object]


class AnalysisOut(BaseModel):
    id: str
    project_id: str
    job_id: str | None
    profile_id: str | None
    profile_name: str
    threshold: float
    engine: str | None
    llm_model: str | None
    use_vision: bool
    notes: list[str]
    cost_usd: float
    created_at: datetime
    candidate_count: int
    selected_count: int
    candidates: list[CandidateOut] = []


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str | None = Field(default=None, max_length=32)
    engine: str = Field(default="auto", pattern="^(auto|llm|signals)$")


class ReselectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float = Field(ge=0, le=100)


class ApiSettingsOut(BaseModel):
    provider: str
    model: str
    effort: str
    key_configured: bool
    api_enabled: bool
    monthly_cap_usd: float
    month_spent_usd: float
    prices_per_mtok: dict[str, float]


class ApiSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_enabled: bool | None = None
    monthly_cap_usd: float | None = Field(default=None, ge=0, le=10_000)


class ApiUsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    provider: str
    model: str
    purpose: str
    project_id: str | None
    candidate_id: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    images: int
    cost_usd: float
    status: str
    detail: str | None


class CostSummaryOut(BaseModel):
    month_spent_usd: float
    monthly_cap_usd: float
    total_spent_usd: float
    calls_this_month: int
    by_month: list[dict[str, object]]
    recent: list[ApiUsageOut]
