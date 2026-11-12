"""Accès paresseux aux modèles locaux de la Phase 5 (chargés une fois par worker).

Chaque accesseur renvoie ``None`` si le modèle n'est pas téléchargé : le pipeline continue
alors sans la fonction concernée et le signale dans le rapport (jamais d'échec silencieux).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np

from app.models_registry import AUDIO_MODELS, PIPER_VOICES
from app.render.facecam import Face


def _asset_path(models_dir: Path, asset_id: str) -> Path:
    asset = AUDIO_MODELS[asset_id]
    return models_dir / asset.subdir / next(iter(asset.files))


class AudioToolkit:
    def __init__(self, models_dir: Path) -> None:
        self.models_dir = models_dir
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}

    def _get(self, key: str, factory):  # type: ignore[no-untyped-def]
        with self._lock:
            if key not in self._cache:
                self._cache[key] = factory()
            return self._cache[key]

    # --- disponibilité (sans charger les modèles)
    def has(self, asset_id: str) -> bool:
        return _asset_path(self.models_dir, asset_id).is_file()

    def voices(self) -> list[str]:
        return [v for v in PIPER_VOICES if self.tts().available(v)]

    # --- modèles
    def music_detector(self):  # type: ignore[no-untyped-def]
        if not self.has("cnn14-16k"):
            return None
        from app.audio.panns import MusicDetector

        return self._get("panns", lambda: MusicDetector(_asset_path(self.models_dir, "cnn14-16k")))

    def separator(self):  # type: ignore[no-untyped-def]
        if not self.has("htdemucs"):
            return None
        from app.audio.separation import MusicSeparator

        return self._get("demucs", lambda: MusicSeparator(_asset_path(self.models_dir, "htdemucs")))

    def tts(self):  # type: ignore[no-untyped-def]
        from app.audio.tts import PiperTTS

        return self._get("tts", lambda: PiperTTS(self.models_dir))

    def detect_faces(self, image: np.ndarray) -> list[Face] | None:
        """Visages d'une image BGR (boîtes normalisées). None si YuNet est absent."""
        if not self.has("yunet"):
            return None
        import cv2

        h, w = image.shape[:2]
        with self._lock:
            det = self._cache.get("yunet")
            if det is None:
                det = cv2.FaceDetectorYN.create(
                    str(_asset_path(self.models_dir, "yunet")), "", (w, h), 0.6, 0.3, 5000
                )
                self._cache["yunet"] = det
            det.setInputSize((w, h))
            _, faces = det.detect(image)
        if faces is None:
            return []
        return [
            Face(float(f[0]) / w, float(f[1]) / h, float(f[2]) / w, float(f[3]) / h, float(f[-1]))
            for f in faces
        ]
