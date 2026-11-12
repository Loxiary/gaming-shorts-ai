"""Synthèse vocale locale (Piper, ONNX, processeur). Voix et licences : app/models_registry."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from app.models_registry import PIPER_VOICES, ModelAsset


@dataclass
class SpokenLine:
    path: Path
    duration: float
    sample_rate: int


class PiperTTS:
    def __init__(self, models_dir: Path) -> None:
        self.models_dir = models_dir
        self._voices: dict[str, object] = {}

    def voice_path(self, voice_id: str) -> Path:
        if voice_id not in PIPER_VOICES:
            raise ValueError(f"Voix inconnue : {voice_id}")
        return self.models_dir / "piper" / f"{voice_id}.onnx"

    def available(self, voice_id: str) -> bool:
        p = self.voice_path(voice_id)
        return p.is_file() and p.with_suffix(".onnx.json").is_file()

    def _voice(self, voice_id: str):  # type: ignore[no-untyped-def]
        if voice_id not in self._voices:
            from piper import PiperVoice

            if not self.available(voice_id):
                raise FileNotFoundError(
                    f"Voix « {voice_id} » absente. Téléchargez-la : "
                    f"python -m app.cli.models download {voice_id}"
                )
            self._voices[voice_id] = PiperVoice.load(self.voice_path(voice_id))
        return self._voices[voice_id]

    def synthesize(self, text: str, voice_id: str, out: Path, speed: float = 1.0) -> SpokenLine:
        """``speed`` > 1 parle plus vite (Piper : length_scale = 1 / speed)."""
        from piper import SynthesisConfig

        voice = self._voice(voice_id)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.wav")
        with wave.open(str(tmp), "wb") as wf:
            voice.synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=1.0 / speed))
        tmp.replace(out)
        with wave.open(str(out), "rb") as wf:
            sr, frames = wf.getframerate(), wf.getnframes()
        return SpokenLine(out, frames / sr, sr)


def voice_asset(voice_id: str) -> ModelAsset:
    return PIPER_VOICES[voice_id]
