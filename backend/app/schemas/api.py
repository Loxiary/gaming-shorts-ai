"""Schémas Pydantic des entrées/sorties de l'API (contrat v1)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


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
    error_message: str | None
    cancel_requested: bool
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class JobDetailOut(JobOut):
    steps: list[JobStepOut]


class ProjectDetailOut(ProjectOut):
    jobs: list[JobOut]


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
