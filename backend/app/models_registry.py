"""Catalogue des modèles locaux téléchargeables (taille, licence, destination).

Rien n'est téléchargé automatiquement par le pipeline : ``python -m app.cli.models``
affiche ce catalogue et télécharge après confirmation, dans ``GSA_DATA_DIR/models``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

HF_PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


@dataclass(frozen=True)
class ModelAsset:
    id: str
    label: str
    purpose: str
    size_mb: float
    license: str
    credit: str | None  # mention à reproduire (licences à attribution)
    files: dict[str, str] = field(default_factory=dict)  # nom de fichier local -> URL
    subdir: str = ""


PIPER_VOICES: dict[str, ModelAsset] = {
    "fr_FR-siwis-medium": ModelAsset(
        id="fr_FR-siwis-medium",
        label="Français — SIWIS (femme)",
        purpose="narration",
        size_mb=63,
        license="CC BY 4.0 (jeu de données SIWIS) — usage commercial autorisé avec crédit",
        credit="Voix de synthèse Piper « fr_FR-siwis » — corpus SIWIS, CC BY 4.0",
        files={
            "fr_FR-siwis-medium.onnx": f"{HF_PIPER}/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx",
            "fr_FR-siwis-medium.onnx.json": (
                f"{HF_PIPER}/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json"
            ),
        },
        subdir="piper",
    ),
    "en_US-joe-medium": ModelAsset(
        id="en_US-joe-medium",
        label="English — Joe (man)",
        purpose="narration",
        size_mb=63,
        license="CC0 (domaine public)",
        credit=None,
        files={
            "en_US-joe-medium.onnx": f"{HF_PIPER}/en/en_US/joe/medium/en_US-joe-medium.onnx",
            "en_US-joe-medium.onnx.json": (
                f"{HF_PIPER}/en/en_US/joe/medium/en_US-joe-medium.onnx.json"
            ),
        },
        subdir="piper",
    ),
}

AUDIO_MODELS: dict[str, ModelAsset] = {
    "cnn14-16k": ModelAsset(
        id="cnn14-16k",
        label="PANNs CNN14 16 kHz (détection de musique, classes AudioSet)",
        purpose="music_detection",
        size_mb=327,
        license="Code MIT ; poids CC BY 4.0 (Kong et al., PANNs, Zenodo 3987831)",
        credit=None,
        files={
            "Cnn14_16k_mAP=0.438.pth": "https://zenodo.org/records/3987831/files/Cnn14_16k_mAP%3D0.438.pth?download=1",
        },
        subdir="panns",
    ),
    "htdemucs": ModelAsset(
        id="htdemucs",
        label="Demucs v4 htdemucs (séparation voix / batterie / basse / autres)",
        purpose="music_separation",
        size_mb=84,
        license="MIT (Meta, Demucs)",
        credit=None,
        files={
            "955717e8-8726e21a.th": "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th",
        },
        subdir="torch/hub/checkpoints",
    ),
    "yunet": ModelAsset(
        id="yunet",
        label="YuNet (détection de visages, sans reconnaissance d'identité)",
        purpose="facecam",
        size_mb=0.3,
        license="MIT (OpenCV Zoo)",
        credit=None,
        files={
            "face_detection_yunet_2023mar.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
            "face_detection_yunet_2023mar.onnx",
        },
        subdir="yunet",
    ),
}

ALL_ASSETS: dict[str, ModelAsset] = {**PIPER_VOICES, **AUDIO_MODELS}
