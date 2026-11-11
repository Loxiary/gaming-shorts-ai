"""Assemblage des adaptateurs utilisés par le worker (remplaçables dans les tests)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.adapters.types import MediaTool, Transcriber, VideoDownloader
from app.core.config import Settings

if TYPE_CHECKING:
    from app.analysis.judge import ClipJudge
    from app.analysis.llm import StructuredLLM


@dataclass
class Adapters:
    downloader: VideoDownloader
    media: MediaTool
    transcriber: Transcriber
    judge: ClipJudge | None = None  # IA d'évaluation des extraits (Phase 3)
    editor: StructuredLLM | None = None  # IA de plan éditorial et traduction (Phase 4)


def default_adapters(settings: Settings) -> Adapters:
    from app.adapters.asr.faster_whisper import FasterWhisperTranscriber
    from app.adapters.downloader.youtube import YouTubeDownloader
    from app.adapters.media.ffmpeg import FfmpegTool
    from app.analysis.judge import AnthropicJudge
    from app.analysis.llm import StructuredLLM

    return Adapters(
        downloader=YouTubeDownloader(settings),
        media=FfmpegTool(),
        transcriber=FasterWhisperTranscriber(settings),
        judge=AnthropicJudge(settings),
        editor=StructuredLLM(settings),
    )
