"""Contrats des adaptateurs (interfaces remplaçables) et types échangés avec le pipeline."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

ProgressCallback = Callable[[float, str | None], None]  # (fraction 0..1, détail lisible)
CancelCheck = Callable[[], None]  # lève JobCancelled si l'utilisateur a annulé


# --------------------------------------------------------------------------- téléchargement


class SourceMetadata(BaseModel):
    external_id: str
    title: str | None = None
    uploader: str | None = None
    channel_id: str | None = None
    channel_url: str | None = None
    upload_date: str | None = None
    duration_seconds: float | None = None
    platform_license: str | None = None
    webpage_url: str | None = None
    estimated_size_bytes: int | None = None
    raw: dict[str, object] = {}


class VideoDownloader(Protocol):
    def fetch_metadata(self, url: str) -> SourceMetadata: ...

    def download(
        self, url: str, dest_dir: Path, on_progress: ProgressCallback, check_cancel: CancelCheck
    ) -> Path: ...


# --------------------------------------------------------------------------- média


class ProbeResult(BaseModel):
    duration_seconds: float
    format_name: str | None
    size_bytes: int | None
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    has_video: bool
    has_audio: bool
    audio_sample_rate: int | None
    audio_channels: int | None
    raw: dict[str, object]


class MediaTool(Protocol):
    def probe(self, path: Path) -> ProbeResult: ...

    def extract_audio(
        self,
        src: Path,
        dst: Path,
        duration_seconds: float,
        on_progress: ProgressCallback,
        check_cancel: CancelCheck,
    ) -> None: ...


# --------------------------------------------------------------------------- transcription


class WordResult(BaseModel):
    start: float
    end: float
    word: str
    probability: float | None = None


class SegmentResult(BaseModel):
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    words: list[WordResult] = []


class TranscriptionResult(BaseModel):
    engine: str
    model: str
    device: str
    compute_type: str
    language: str | None
    language_probability: float | None
    audio_duration_seconds: float
    processing_seconds: float
    model_load_seconds: float
    vram_peak_used_mib: int | None = None
    vram_baseline_used_mib: int | None = None
    warnings: list[str] = []
    options: dict[str, object] = {}
    segments: list[SegmentResult]


class Transcriber(Protocol):
    def transcribe(
        self, audio_path: Path, on_progress: ProgressCallback, check_cancel: CancelCheck
    ) -> TranscriptionResult: ...
