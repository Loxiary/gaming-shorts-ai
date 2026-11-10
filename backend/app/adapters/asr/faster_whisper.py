"""Transcription locale avec faster-whisper (CTranslate2).

- Le modèle doit déjà être présent dans ``GSA_DATA_DIR/models`` : le pipeline ne télécharge
  jamais de modèle (voir ``python -m app.cli.models``).
- GPU NVIDIA si disponible (bibliothèques CUDA fournies par les paquets pip ``nvidia-*``),
  sinon CPU. Le repli éventuel est signalé dans les avertissements du résultat.
- Le modèle est déchargé après chaque transcription pour libérer la VRAM.
- La transcription produite est la transcription SOURCE fidèle (aucune réécriture).
"""

from __future__ import annotations

import gc
import glob
import logging
import os
import sys
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

from app.adapters.gpu import GpuMemorySampler
from app.adapters.types import (
    CancelCheck,
    ProgressCallback,
    SegmentResult,
    TranscriptionResult,
    WordResult,
)
from app.core.config import Settings
from app.workers.errors import StepError

logger = logging.getLogger("app.adapters.faster_whisper")

_DLL_DIRS_ADDED = False


def ensure_cuda_dlls() -> None:
    """Rend visibles les DLL CUDA (cuBLAS, cuDNN) installées par pip sous Windows."""
    global _DLL_DIRS_ADDED
    if _DLL_DIRS_ADDED or sys.platform != "win32":
        return
    base = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for directory in glob.glob(str(base / "*" / "bin")):
        os.add_dll_directory(directory)
        os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
    _DLL_DIRS_ADDED = True


def load_wav_16k_mono(path: Path) -> np.ndarray:
    try:
        with wave.open(str(path), "rb") as w:
            if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise StepError(
                    "Audio inattendu : WAV PCM 16 bits, 16 kHz, mono requis "
                    f"(reçu {w.getframerate()} Hz, {w.getnchannels()} canal(aux))."
                )
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as exc:
        raise StepError("Fichier audio illisible ou tronqué.", technical=str(exc)) from exc
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


class FasterWhisperTranscriber:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _resolve_device(self) -> tuple[str, str]:
        import ctranslate2

        device = self.settings.whisper_device
        if device == "auto":
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        compute = self.settings.whisper_compute_type
        if compute == "auto":
            compute = "int8_float16" if device == "cuda" else "int8"
        return device, compute

    def _load(self, model_dir: Path, warnings: list[str]) -> tuple[Any, str, str]:
        from faster_whisper import WhisperModel

        device, compute = self._resolve_device()
        try:
            return (
                WhisperModel(str(model_dir), device=device, compute_type=compute),
                device,
                compute,
            )
        except (RuntimeError, ValueError) as exc:
            if device != "cuda" or self.settings.whisper_device == "cuda":
                raise StepError(
                    f"Impossible de charger le modèle sur {device} : {exc}", technical=repr(exc)
                ) from exc
            message = f"GPU indisponible ({exc}) : transcription sur CPU (plus lente)."
            logger.warning(message)
            warnings.append(message)
            return WhisperModel(str(model_dir), device="cpu", compute_type="int8"), "cpu", "int8"

    def transcribe(
        self, audio_path: Path, on_progress: ProgressCallback, check_cancel: CancelCheck
    ) -> TranscriptionResult:
        model_dir = self.settings.whisper_model_dir
        if not (model_dir / "model.bin").is_file():
            raise StepError(
                f"Modèle de transcription absent ({model_dir}). Téléchargez-le avec : "
                "cd backend; .\\.venv\\Scripts\\python.exe -m app.cli.models download"
            )
        ensure_cuda_dlls()
        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # aucun accès réseau pendant l'inférence
        audio = load_wav_16k_mono(audio_path)
        duration = len(audio) / 16000
        warnings: list[str] = []
        options = {
            "language": self.settings.whisper_language or None,
            "beam_size": self.settings.whisper_beam_size,
            "word_timestamps": True,
            "vad_filter": self.settings.whisper_vad,
            # Limite les boucles d'hallucination sur musique / bruit de jeu.
            "condition_on_previous_text": False,
        }

        on_progress(0.0, "Chargement du modèle…")
        model = None
        with GpuMemorySampler() as sampler:
            t0 = time.perf_counter()
            model, device, compute = self._load(model_dir, warnings)
            load_seconds = time.perf_counter() - t0
            try:
                t1 = time.perf_counter()
                segments_iter, info = model.transcribe(audio, **options)
                segments: list[SegmentResult] = []
                for seg in segments_iter:
                    check_cancel()
                    segments.append(
                        SegmentResult(
                            start=round(seg.start, 3),
                            end=round(max(seg.end, seg.start), 3),
                            text=seg.text.strip(),
                            avg_logprob=seg.avg_logprob,
                            no_speech_prob=seg.no_speech_prob,
                            words=[
                                WordResult(
                                    start=round(w.start, 3),
                                    end=round(max(w.end, w.start), 3),
                                    word=w.word,
                                    probability=round(w.probability, 4),
                                )
                                for w in (seg.words or [])
                            ],
                        )
                    )
                    if duration > 0:
                        on_progress(
                            min(seg.end / duration, 0.99),
                            f"{seg.end / 60:.1f} / {duration / 60:.1f} min transcrites",
                        )
                processing = time.perf_counter() - t1
            finally:
                del model
                gc.collect()

        on_progress(1.0, f"{len(segments)} segments")
        from faster_whisper import __version__ as fw_version

        return TranscriptionResult(
            engine=f"faster-whisper {fw_version}",
            model=self.settings.whisper_model,
            device=device,
            compute_type=compute,
            language=info.language,
            language_probability=round(info.language_probability, 4),
            audio_duration_seconds=round(duration, 3),
            processing_seconds=round(processing, 2),
            model_load_seconds=round(load_seconds, 2),
            vram_peak_used_mib=sampler.peak,
            vram_baseline_used_mib=sampler.baseline,
            warnings=warnings,
            options=options,
            segments=segments,
        )
