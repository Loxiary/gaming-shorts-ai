"""Schémas Pydantic des entrées/sorties de l'API (contrat v1)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import RightsStatus


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    game: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    is_test: bool = False

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le nom du projet ne peut pas être vide")
        return value

    @field_validator("game", "description")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    game: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Le nom du projet ne peut pas être vide")
        return value

    @field_validator("game", "description")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class JobCounts(BaseModel):
    total: int = 0
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    game: str | None
    description: str | None
    is_test: bool
    created_at: datetime
    updated_at: datetime
    job_counts: JobCounts = Field(default_factory=JobCounts)


class JobStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    name: str
    label: str
    status: str
    progress: float
    detail: str | None
    output: dict[str, Any] | None = Field(default=None, validation_alias="output_json")
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None

    @field_validator("output", mode="before")
    @classmethod
    def _parse_output(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    project_name: str
    kind: str
    kind_label: str
    is_demo: bool
    status: str
    progress: float
    current_step: str | None
    current_step_label: str | None = None
    current_step_detail: str | None = None
    error_message: str | None
    cancel_requested: bool
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class JobDetailOut(JobOut):
    steps: list[JobStepOut]


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: str
    url: str
    external_id: str
    rights_status: RightsStatus
    rights_note: str | None
    title: str | None
    uploader: str | None
    channel_url: str | None
    upload_date: str | None
    platform_license: str | None
    duration_seconds: float | None
    media_available: bool = False
    media_size_bytes: int | None
    audio_available: bool = False
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool | None
    created_at: datetime


class SourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rights_status: RightsStatus | None = None
    rights_note: str | None = Field(default=None, max_length=2000)


class TranscriptSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    engine: str
    model: str
    device: str
    compute_type: str
    language: str | None
    language_probability: float | None
    audio_duration_seconds: float | None
    processing_seconds: float | None
    segment_count: int = 0
    created_at: datetime


class WordOut(BaseModel):
    start: float
    end: float
    word: str
    probability: float | None = None


class TranscriptSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    start_seconds: float
    end_seconds: float
    text: str
    avg_logprob: float | None
    no_speech_prob: float | None
    words: list[WordOut] = Field(default_factory=list, validation_alias="words_json")

    @field_validator("words", mode="before")
    @classmethod
    def _parse_words(cls, value: object) -> object:
        if value is None:
            return []
        return json.loads(value) if isinstance(value, str) else value


class TranscriptOut(TranscriptSummaryOut):
    segments: list[TranscriptSegmentOut]


class ProjectDetailOut(ProjectOut):
    jobs: list[JobOut]
    source: SourceOut | None = None
    transcript: TranscriptSummaryOut | None = None
    files_size_bytes: int = 0


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urls: list[str] = Field(min_length=1, max_length=20)
    rights_status: RightsStatus = RightsStatus.UNKNOWN
    rights_note: str | None = Field(default=None, max_length=2000)
    game: str | None = Field(default=None, max_length=120)

    @field_validator("urls")
    @classmethod
    def _clean_urls(cls, value: list[str]) -> list[str]:
        cleaned = [u.strip() for u in value if u.strip()]
        if not cleaned:
            raise ValueError("Aucun lien fourni")
        return cleaned

    @field_validator("game", "rights_note")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class ImportResultItem(BaseModel):
    url: str
    status: Literal["created", "duplicate", "rejected"]
    project_id: str | None = None
    job_id: str | None = None
    message: str | None = None


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=32)
    kind: str = Field(min_length=1, max_length=50)


class JobKindOut(BaseModel):
    kind: str
    label: str
    description: str
    is_demo: bool
    steps: list[str]


class WorkerStatusOut(BaseModel):
    alive: bool
    last_seen_at: datetime | None
    worker_id: str | None


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    phase: str
    database: str
    database_detail: str | None = None
    worker: WorkerStatusOut


class DataDirOut(BaseModel):
    name: str
    path: str
    exists: bool
    size_bytes: int


class ToolStatusOut(BaseModel):
    name: str
    found: bool
    path: str | None


class FeatureStatusOut(BaseModel):
    name: str
    available: bool
    note: str


class GpuOut(BaseModel):
    name: str
    memory_total_mib: int
    memory_used_mib: int
    memory_free_mib: int
    driver_version: str


class AsrConfigOut(BaseModel):
    engine: str
    model: str
    model_dir: str
    model_present: bool
    device: str
    compute_type: str
    language: str
    vad: bool


class SystemInfoOut(BaseModel):
    app: str
    version: str
    phase: str
    api_host: str
    api_port: int
    data_dir: str
    database_path: str
    database_size_bytes: int
    disk_total_bytes: int
    disk_free_bytes: int
    data_dirs: list[DataDirOut]
    tools: list[ToolStatusOut]
    features: list[FeatureStatusOut]
    demo_step_seconds: float
    worker_stale_seconds: float
    gpu: GpuOut | None = None
    asr: AsrConfigOut | None = None
    max_download_height: int = 1080
    max_source_minutes: int = 240
