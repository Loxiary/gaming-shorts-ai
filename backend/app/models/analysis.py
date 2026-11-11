"""Entités de la Phase 3 : profils de montage, analyses, candidats, scores, coûts API, réglages."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models.base import Base, UTCDateTime, new_id

# Critères de scoring du cahier des charges (§7). L'ordre est celui de l'affichage.
CRITERIA: dict[str, str] = {
    "hook": "Force de l'accroche",
    "entertainment": "Divertissement / intensité",
    "standalone": "Compréhension autonome",
    "narrative": "Progression narrative",
    "retention": "Potentiel de rétention",
    "originality": "Originalité / valeur ajoutée",
    "av_quality": "Qualité audio-visuelle",
}

MIN_CLIP_SECONDS = 61.0  # contrainte impérative du cahier des charges
MAX_CLIP_SECONDS = 180.0


class EditingProfile(Base):
    __tablename__ = "editing_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    # Angle éditorial transmis à l'IA (ex. « privilégier l'humour »).
    editorial_focus: Mapped[str | None] = mapped_column(Text)
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)
    weights_json: Mapped[str] = mapped_column(Text, nullable=False)
    output_language: Mapped[str] = mapped_column(String(10), nullable=False, default="fr")
    min_duration: Mapped[float] = mapped_column(Float, nullable=False, default=MIN_CLIP_SECONDS)
    max_duration: Mapped[float] = mapped_column(Float, nullable=False, default=MAX_CLIP_SECONDS)
    max_candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    use_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Montage (Phase 4). server_default : profils existants complétés à la migration.
    # Sous-titres : « source » (verbatim), « translate » (traduction IA), « off ».
    subtitle_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="source", server_default="source"
    )
    subtitle_style_json: Mapped[str | None] = mapped_column(Text)
    layout: Mapped[str] = mapped_column(  # « blur » (fond flouté) ou « fill » (plein cadre)
        String(20), nullable=False, default="blur", server_default="blur"
    )
    zoom_intensity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.12, server_default="0.12"
    )
    hook_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    cta_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    cta_text: Mapped[str | None] = mapped_column(Text)  # vide = proposé par l'IA
    render_encoder: Mapped[str] = mapped_column(
        String(20), nullable=False, default="libx264", server_default="libx264"
    )

    # --- Audio et facecam (Phase 5). Niveaux en dB.
    narration_mode: Mapped[str] = mapped_column(  # « auto » : l'IA décide ; « off »
        String(20), nullable=False, default="auto", server_default="auto"
    )
    narration_voice: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="fr_FR-siwis-medium",
        server_default="fr_FR-siwis-medium",
    )
    narration_speed: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, server_default="1.0"
    )
    narration_level_db: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    game_level_db: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    music_mode: Mapped[str] = mapped_column(  # « library » (bibliothèque locale) ou « off »
        String(20), nullable=False, default="library", server_default="library"
    )
    music_level_db: Mapped[float] = mapped_column(
        Float, nullable=False, default=-18.0, server_default="-18"
    )
    source_music_mode: Mapped[str] = mapped_column(  # « attenuate », « detect » ou « off »
        String(20), nullable=False, default="attenuate", server_default="attenuate"
    )
    source_music_reduction_db: Mapped[float] = mapped_column(
        Float, nullable=False, default=15.0, server_default="15"
    )
    facecam_mode: Mapped[str] = mapped_column(  # « crop » (exclure par recadrage) ou « off »
        String(20), nullable=False, default="crop", server_default="crop"
    )

    # --- Transitions et effets ponctuels (Phase 7)
    effects_mode: Mapped[str] = mapped_column(  # « auto » : l'IA propose ; « off »
        String(20), nullable=False, default="auto", server_default="auto"
    )
    transition_in: Mapped[str] = mapped_column(  # none | fade | zoom
        String(20), nullable=False, default="zoom", server_default="zoom"
    )
    transition_out: Mapped[str] = mapped_column(  # none | fade
        String(20), nullable=False, default="fade", server_default="fade"
    )
    sfx_mode: Mapped[str] = mapped_column(  # « auto » : bruitages sur effets et transitions
        String(20), nullable=False, default="auto", server_default="auto"
    )
    sfx_level_db: Mapped[float] = mapped_column(
        Float, nullable=False, default=-14.0, server_default="-14"
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint("threshold >= 0 AND threshold <= 100", name="threshold_range"),
        CheckConstraint("zoom_intensity >= 0 AND zoom_intensity <= 0.5", name="zoom_range"),
        CheckConstraint(
            f"min_duration >= {MIN_CLIP_SECONDS} AND max_duration <= {MAX_CLIP_SECONDS} "
            "AND min_duration <= max_duration",
            name="duration_bounds",
        ),
        CheckConstraint("max_candidates >= 1 AND max_candidates <= 50", name="max_candidates"),
    )


class ClipAnalysis(Base):
    """Une exécution d'analyse d'une source avec un profil (instantané du profil conservé)."""

    __tablename__ = "clip_analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("editing_profiles.id", ondelete="SET NULL")
    )
    profile_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    # « llm » (IA) ou « signals » (estimation locale sans IA, clairement signalée).
    engine: Mapped[str | None] = mapped_column(String(20))
    llm_model: Mapped[str | None] = mapped_column(String(80))
    use_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    signals_path: Mapped[str | None] = mapped_column(String(500))
    notes_json: Mapped[str | None] = mapped_column(Text)  # avertissements globaux
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    candidates: Mapped[list[ClipCandidate]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ClipCandidate.position",
    )


class SceneSegment(Base):
    __tablename__ = "scene_segments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_media_id: Mapped[str] = mapped_column(
        ForeignKey("source_media.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    cut_score: Mapped[float | None] = mapped_column(Float)  # intensité du changement en entrée

    __table_args__ = (
        UniqueConstraint("source_media_id", "position", name="uq_scene_segments_position"),
    )


class ClipCandidate(Base):
    __tablename__ = "clip_candidates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("clip_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    peak_seconds: Mapped[float | None] = mapped_column(Float)
    signal_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    signals_json: Mapped[str | None] = mapped_column(Text)
    transcript_excerpt: Mapped[str | None] = mapped_column(Text)
    frames_json: Mapped[str | None] = mapped_column(Text)  # [{t, path}]
    # « pending », « scored » (IA), « signals_only », « failed », « refused »
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    summary: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    events_json: Mapped[str | None] = mapped_column(Text)
    warnings_json: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    overall_score: Mapped[float | None] = mapped_column(Float)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(200))
    error_message: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(String(80))
    raw_response_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    analysis: Mapped[ClipAnalysis] = relationship(back_populates="candidates")
    scores: Mapped[list[ClipScore]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("analysis_id", "position", name="uq_clip_candidates_position"),
        CheckConstraint(
            f"end_seconds - start_seconds >= {MIN_CLIP_SECONDS - 0.001} "
            f"AND end_seconds - start_seconds <= {MAX_CLIP_SECONDS + 0.001}",
            name="duration_61_180",
        ),
    )


class ClipScore(Base):
    __tablename__ = "clip_scores"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("clip_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criterion: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 0..10
    justification: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped[ClipCandidate] = relationship(back_populates="scores")

    __table_args__ = (
        UniqueConstraint("candidate_id", "criterion", name="uq_clip_scores_criterion"),
        CheckConstraint("score >= 0 AND score <= 10", name="score_range"),
    )


class ApiUsage(Base):
    """Journal de chaque appel d'API payant (coût estimé à partir des jetons facturés)."""

    __tablename__ = "api_usage"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(32))
    job_id: Mapped[str | None] = mapped_column(String(32))
    candidate_id: Mapped[str | None] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    images: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ok | refused | error
    request_id: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_api_usage_created_at", "created_at"),)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
