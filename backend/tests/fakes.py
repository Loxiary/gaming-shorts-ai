"""Adaptateurs factices pour les tests (aucun accès réseau, aucun modèle IA).

Le faux téléchargeur produit une VRAIE vidéo synthétique avec FFmpeg, afin que les étapes
ffprobe et extraction audio soient testées avec les vrais outils.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.adapters.types import (
    CancelCheck,
    ProgressCallback,
    SegmentResult,
    SourceMetadata,
    TranscriptionResult,
    WordResult,
)
from app.workers.errors import StepError

requires_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="FFmpeg absent du PATH"
)


def make_test_video(path: Path, seconds: float = 3.0, *, audio: bool = True) -> Path:
    """Vidéo MP4 H.264 (+ AAC si audio) générée par FFmpeg : mire + bip 440 Hz."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=320x240:rate=30:duration={seconds}",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-shortest"] if audio else ["-an"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True)
    return path


class FakeDownloader:
    def __init__(
        self,
        *,
        seconds: float = 3.0,
        audio: bool = True,
        metadata_error: StepError | None = None,
        download_error: StepError | None = None,
        cancel_during_download: bool = False,
    ) -> None:
        self.seconds = seconds
        self.audio = audio
        self.metadata_error = metadata_error
        self.download_error = download_error
        self.cancel_during_download = cancel_during_download
        self.metadata_calls = 0
        self.download_calls = 0
        self.on_cancel_point = None  # callable appelé avant le point d'annulation

    def fetch_metadata(self, url: str) -> SourceMetadata:
        self.metadata_calls += 1
        if self.metadata_error:
            raise self.metadata_error
        return SourceMetadata(
            external_id=url.rsplit("=", 1)[-1],
            title="Partie GTA de test",
            uploader="Chaîne de test",
            channel_url="https://www.youtube.com/@test",
            upload_date="20261101",
            duration_seconds=self.seconds,
            platform_license="Creative Commons Attribution license (reuse allowed)",
            estimated_size_bytes=100_000,
            raw={"id": url.rsplit("=", 1)[-1], "title": "Partie GTA de test"},
        )

    def download(
        self, url: str, dest_dir: Path, on_progress: ProgressCallback, check_cancel: CancelCheck
    ) -> Path:
        self.download_calls += 1
        if self.download_error:
            error, self.download_error = self.download_error, None  # échoue une seule fois
            raise error
        on_progress(0.5, "50 Mo / 100 Mo")
        if self.cancel_during_download:
            if self.on_cancel_point:
                self.on_cancel_point()
            check_cancel()
        path = make_test_video(dest_dir / "source.mp4", self.seconds, audio=self.audio)
        on_progress(1.0, "terminé")
        return path


class FakeTranscriber:
    def __init__(self) -> None:
        self.calls = 0
        self.audio_paths: list[Path] = []

    def transcribe(
        self, audio_path: Path, on_progress: ProgressCallback, check_cancel: CancelCheck
    ) -> TranscriptionResult:
        self.calls += 1
        self.audio_paths.append(audio_path)
        assert audio_path.is_file()
        on_progress(0.5, "moitié")
        return TranscriptionResult(
            engine="fake 1.0",
            model="fake-model",
            device="cpu",
            compute_type="int8",
            language="fr",
            language_probability=0.99,
            audio_duration_seconds=3.0,
            processing_seconds=0.5,
            model_load_seconds=0.1,
            options={"word_timestamps": True},
            segments=[
                SegmentResult(
                    start=0.0,
                    end=1.4,
                    text="Attention, il arrive par la gauche !",
                    words=[
                        WordResult(start=0.0, end=0.6, word=" Attention,", probability=0.98),
                        WordResult(start=0.7, end=1.4, word=" il arrive", probability=0.95),
                    ],
                ),
                SegmentResult(start=1.6, end=2.9, text="On a réussi la mission."),
            ],
        )
