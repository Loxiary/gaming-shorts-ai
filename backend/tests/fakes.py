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


# --------------------------------------------------------------------------- Phase 3


def make_bursty_video(
    path: Path, seconds: float = 150.0, bursts: tuple[float, ...] = (40, 100)
) -> Path:
    """Vidéo synthétique dont l'audio est calme sauf de courtes rafales fortes (moments forts)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cond = "+".join(f"between(t,{b},{b + 4})" for b in bursts) or "0"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=320x240:rate=15:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=330:sample_rate=44100:duration={seconds}",
            "-filter_complex",
            f"[1:a]volume='if({cond},1.0,0.03)':eval=frame[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


class SpeechTranscriber(FakeTranscriber):
    """Une phrase toutes les 8 s sur toute la durée (mots horodatés)."""

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self.seconds = seconds

    def transcribe(self, audio_path, on_progress, check_cancel):  # type: ignore[no-untyped-def]
        base = super().transcribe(audio_path, on_progress, check_cancel)
        segments = []
        t = 1.0
        i = 0
        while t + 5 < self.seconds:
            words = [WordResult(start=t + k, end=t + k + 0.8, word=f" mot{k}") for k in range(5)]
            segments.append(
                SegmentResult(start=t, end=t + 5, text=f"Phrase numéro {i} du test.", words=words)
            )
            t += 8
            i += 1
        return base.model_copy(
            update={"segments": segments, "audio_duration_seconds": self.seconds}
        )


class FakeJudge:
    """IA simulée : notes fixes, coût fictif enregistré, budget vérifié comme le vrai juge."""

    model = "fake-claude"
    configured = True

    def __init__(self, score: int = 8, fail_on: set[int] | None = None) -> None:
        self.score = score
        self.calls = 0
        self.fail_on = fail_on or set()
        self.inputs = []

    def judge(self, context, item, budget_check, record_usage):  # type: ignore[no-untyped-def]
        from app.analysis.judge import (
            ClipAssessment,
            CriterionAssessment,
            JudgeResult,
            KeyEvent,
            Usage,
        )

        budget_check(0.01)
        self.calls += 1
        self.inputs.append(item)
        if self.calls in self.fail_on:
            raise StepError("Connexion à l'API Anthropic impossible.")
        crit = CriterionAssessment(score=self.score, justification="Justification simulée.")
        assessment = ClipAssessment(
            summary="Résumé factuel simulé.",
            reason="Raison simulée.",
            hook=crit,
            entertainment=crit,
            standalone=crit,
            narrative=crit,
            retention=crit,
            originality=crit,
            av_quality=crit,
            confidence=0.8,
            key_events=[KeyEvent(t=item.start + 5, description="Événement simulé")],
            suggested_start=item.start,
            suggested_end=item.end,
            self_contained=True,
            warnings=[],
        )
        result = JudgeResult(
            "scored",
            self.model,
            assessment=assessment,
            usage=Usage(input_tokens=5000, output_tokens=1000),
            request_id=f"req_{self.calls}",
            raw=assessment.model_dump_json(),
        )
        record_usage(result, len(item.frames))
        return result


class FakeEditor:
    """IA de montage simulée : plan éditorial et traduction déterministes, coût fictif."""

    model = "fake-editor"
    configured = True

    def __init__(
        self,
        hook_kind: str = "original",
        narration: list[tuple[float, str]] | None = None,
        music_mood: str = "",
        effects: list[tuple[float, str, float]] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.systems: list[str] = []
        self.hook_kind = hook_kind
        self.narration = narration or []
        self.music_mood = music_mood
        self.effects = effects or []

    def call(
        self,
        *,
        system,
        content,
        schema,
        budget_check,
        record,
        validate=None,  # type: ignore[no-untyped-def]
        max_tokens=8000,
    ):
        from app.analysis.judge import Usage
        from app.analysis.llm import LLMResult
        from app.render import editorial as ed

        budget_check(0.01)
        self.calls.append(schema.__name__)
        self.systems.append(system)
        if schema is ed.Translation:
            body = content[0]["text"].split("\n")[1:]
            parsed = ed.Translation(
                sentences=[
                    ed.TranslatedSentence(
                        index=int(line.split(":", 1)[0]),
                        text=f"Phrase traduite {line.split(':', 1)[0]}.",
                    )
                    for line in body
                    if ":" in line
                ]
            )
        else:
            parsed = ed.EditorialPlan(
                hook_text="Une partie qui démarre fort",
                hook_kind=self.hook_kind,
                hook_reason="test",
                cta_text="Tu aurais fait pareil ?",
                keywords=["numéro", "test"],
                zooms=[ed.ZoomMoment(t=10, duration=2, reason="test")],
                warnings=[],
                narration_needed=bool(self.narration),
                narration_reason="Contexte utile (test)." if self.narration else "",
                narration=[ed.NarrationLine(t=t, text=x) for t, x in self.narration],
                music_mood=self.music_mood,
                effects=[
                    ed.EffectMoment(t=t, kind=k, duration=d, reason="test")  # type: ignore[arg-type]
                    for t, k, d in self.effects
                ],
            )
        if validate:
            validate(parsed)
        result = LLMResult(
            "ok",
            self.model,
            parsed=parsed,
            usage=Usage(input_tokens=2000, output_tokens=500),
            request_id="req_ed",
        )
        record(result)
        return result
