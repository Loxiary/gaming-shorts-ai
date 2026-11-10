"""Entités persistées de la Phase 1 : Project, Job, JobStep et WorkerHeartbeat."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models.base import Base, UTCDateTime, new_id


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING)
TERMINAL_JOB_STATUSES = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _in_list(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{v.value}'" for v in enum)
    return f"{column} IN ({values})"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    game: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    source: Mapped[SourceMedia | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    jobs: Mapped[list[Job]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Job.created_at.desc()",
    )

    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_empty"),)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=JobStatus.QUEUED)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_step: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_by: Mapped[str | None] = mapped_column(String(120))
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="jobs")
    steps: Mapped[list[JobStep]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="JobStep.position",
    )

    __table_args__ = (
        CheckConstraint(_in_list("status", JobStatus), name="status_valid"),
        CheckConstraint("progress >= 0 AND progress <= 1", name="progress_range"),
        Index("ix_jobs_status_created_at", "status", "created_at"),
        # Anti-doublon : un seul job actif (queued/running) d'un même type par projet.
        Index(
            "uq_jobs_active_project_kind",
            "project_id",
            "kind",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )


class JobStep(Base):
    __tablename__ = "job_steps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=StepStatus.PENDING)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    detail: Mapped[str | None] = mapped_column(String(300))
    # Sortie JSON de l'étape (chemins relatifs, mesures, versions) : provenance et reprise.
    output_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    job: Mapped[Job] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("job_id", "position", name="uq_job_steps_job_position"),
        CheckConstraint(_in_list("status", StepStatus), name="status_valid"),
    )


class WorkerHeartbeat(Base):
    """Présence des workers, pour signaler dans l'UI qu'aucun worker ne traite la file."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class RightsStatus(StrEnum):
    """Statut des droits DÉCLARÉ par l'utilisateur. Informatif : ne bloque jamais rien."""

    UNKNOWN = "unknown"
    OWNED = "owned"  # l'utilisateur est le créateur de la vidéo
    AUTHORIZED = "authorized"  # autorisation obtenue du créateur
    LICENSED = "licensed"  # licence permettant la réutilisation (ex. Creative Commons)


class SourceMedia(Base):
    """Source vidéo d'un projet (une par projet en V1)."""

    __tablename__ = "source_media"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "youtube"
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rights_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RightsStatus.UNKNOWN
    )
    rights_note: Mapped[str | None] = mapped_column(Text)

    # Métadonnées de la plateforme (étape validating_source)
    title: Mapped[str | None] = mapped_column(String(500))
    uploader: Mapped[str | None] = mapped_column(String(300))
    channel_id: Mapped[str | None] = mapped_column(String(100))
    channel_url: Mapped[str | None] = mapped_column(String(500))
    upload_date: Mapped[str | None] = mapped_column(String(8))  # AAAAMMJJ
    platform_license: Mapped[str | None] = mapped_column(String(200))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[str | None] = mapped_column(Text)

    # Fichiers (chemins relatifs à la racine data) et analyse technique
    media_path: Mapped[str | None] = mapped_column(String(500))
    media_size_bytes: Mapped[int | None] = mapped_column(Integer)
    audio_path: Mapped[str | None] = mapped_column(String(500))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    video_codec: Mapped[str | None] = mapped_column(String(50))
    audio_codec: Mapped[str | None] = mapped_column(String(50))
    has_audio: Mapped[bool | None] = mapped_column(Boolean)
    probe_json: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="source")
    transcripts: Mapped[list[Transcript]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Transcript.created_at.desc()",
    )

    __table_args__ = (
        # Anti-doublon : une même vidéo ne peut être importée qu'une fois.
        UniqueConstraint("source_type", "external_id", name="uq_source_media_type_external"),
        CheckConstraint(_in_list("rights_status", RightsStatus), name="rights_status_valid"),
    )


class Transcript(Base):
    """Transcription SOURCE (verbatim). Les traductions seront stockées à part (kind)."""

    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_media_id: Mapped[str] = mapped_column(
        ForeignKey("source_media.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="source")
    engine: Mapped[str] = mapped_column(String(50), nullable=False)  # ex. faster-whisper 1.2.1
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    device: Mapped[str] = mapped_column(String(20), nullable=False)
    compute_type: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str | None] = mapped_column(String(10))
    language_probability: Mapped[float | None] = mapped_column(Float)
    audio_duration_seconds: Mapped[float | None] = mapped_column(Float)
    processing_seconds: Mapped[float | None] = mapped_column(Float)
    options_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    source: Mapped[SourceMedia] = relationship(back_populates="transcripts")
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="transcript",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TranscriptSegment.position",
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    transcript_id: Mapped[str] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    avg_logprob: Mapped[float | None] = mapped_column(Float)
    no_speech_prob: Mapped[float | None] = mapped_column(Float)
    words_json: Mapped[str | None] = mapped_column(Text)  # [{start, end, word, probability}]

    transcript: Mapped[Transcript] = relationship(back_populates="segments")

    __table_args__ = (
        UniqueConstraint("transcript_id", "position", name="uq_transcript_segments_position"),
        CheckConstraint("end_seconds >= start_seconds", name="segment_order"),
    )
