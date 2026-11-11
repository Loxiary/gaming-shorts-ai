from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RenderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str | None = Field(default=None, max_length=32)


class ExportConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged: bool


class RenderOut(BaseModel):
    id: str
    project_id: str
    candidate_id: str | None
    job_id: str | None
    job_status: str | None
    job_error: str | None
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    profile_name: str
    plan: dict[str, Any] | None
    plan_engine: str | None
    subtitles: list[dict[str, Any]]
    subtitle_language: str | None
    subtitles_are_translation: bool
    video_url: str | None
    output_size_bytes: int | None
    qc: dict[str, Any] | None
    qc_passed: bool | None
    risk_report: dict[str, Any] | None
    audio_report: dict[str, Any] | None = None
    facecam: dict[str, Any] | None = None
    credits: list[dict[str, Any]] = []
    preview_audio_url: str | None = None
    files_purged: bool = False
    export_warnings: list[str]
    ready: bool
    cost_usd: float
    export_status: str
    exported_path: str | None
    export_confirmed_at: datetime | None
    acknowledged_warnings: list[str]
    created_at: datetime


class BatchRenderOut(BaseModel):
    created: list[RenderOut]
    skipped_candidate_ids: list[str]
