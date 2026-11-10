"""Assemblage des adaptateurs utilisés par le worker (remplaçables dans les tests)."""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.types import MediaTool, Transcriber, VideoDownloader
from app.core.config import Settings


@dataclass
class Adapters:
    downloader: VideoDownloader
    media: MediaTool
    transcriber: Transcriber


def default_adapters(settings: Settings) -> Adapters:
    from app.adapters.asr.faster_whisper import FasterWhisperTranscriber
    from app.adapters.downloader.youtube import YouTubeDownloader
    from app.adapters.media.ffmpeg import FfmpegTool

    return Adapters(
        downloader=YouTubeDownloader(settings),
        media=FfmpegTool(),
        transcriber=FasterWhisperTranscriber(settings),
    )
