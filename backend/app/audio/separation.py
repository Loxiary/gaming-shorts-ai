"""Séparation de sources (Demucs v4 htdemucs) et atténuation de la musique d'origine.

Demucs sépare voix / batterie / basse / « autres ». Les bruitages d'un jeu se retrouvent
surtout dans « autres » et « batterie », AVEC la musique : l'atténuation ne s'applique donc
qu'aux secondes où la musique est détectée, et elle réduit aussi les bruitages de ces
passages. Le résultat n'est jamais parfait ; il est signalé comme tel dans le rapport.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from app.audio.safe_load import safe_torch_load

DEMUCS_SR = 44_100
SOURCES = ("drums", "bass", "other", "vocals")


class MusicSeparator:
    def __init__(self, checkpoint: Path, threads: int | None = None) -> None:
        if not checkpoint.is_file():
            raise FileNotFoundError(
                f"Modèle de séparation absent ({checkpoint}). Téléchargez-le : "
                "python -m app.cli.models download htdemucs"
            )
        from demucs.htdemucs import HTDemucs

        pkg = safe_torch_load(checkpoint, extra=[HTDemucs])
        if pkg.get("klass") is not HTDemucs:
            raise ValueError("Paquet Demucs inattendu (classe de modèle non reconnue).")
        self.model = HTDemucs(*pkg["args"], **pkg["kwargs"])
        self.model.load_state_dict(pkg["state"])
        self.model.eval()
        if tuple(self.model.sources) != SOURCES:
            raise ValueError(f"Sources inattendues : {self.model.sources}")
        if threads:
            torch.set_num_threads(threads)

    @torch.inference_mode()
    def separate(self, stereo: np.ndarray) -> dict[str, np.ndarray]:
        """``stereo`` : (2, n) float32 à 44,1 kHz. Retourne chaque source en (2, n)."""
        from demucs.apply import apply_model

        mix = torch.from_numpy(np.ascontiguousarray(stereo, dtype=np.float32))
        ref = mix.mean(0)
        mean, std = ref.mean(), ref.std() + 1e-8
        out = apply_model(
            self.model,
            ((mix - mean) / std)[None],
            device="cpu",
            split=True,
            overlap=0.25,
            progress=False,
        )[0]
        out = out * std + mean
        return {name: out[i].numpy() for i, name in enumerate(SOURCES)}


def music_gain_curve(
    music_prob: list[float],
    n_samples: int,
    sr: int,
    threshold: float,
    reduction_db: float,
    ramp_s: float = 0.5,
) -> np.ndarray:
    """Gain par échantillon pour les sources non vocales : -reduction_db où la musique est
    détectée (probabilité >= seuil), 0 dB ailleurs, avec des transitions douces."""
    target = 10 ** (-reduction_db / 20)
    per_sec = np.array([target if p >= threshold else 1.0 for p in music_prob], dtype=np.float32)
    if len(per_sec) == 0:
        return np.ones(n_samples, dtype=np.float32)
    # Lissage (moyenne glissante sur ~ramp) pour éviter les pompages audibles.
    k = max(1, int(round(ramp_s * 2)))
    per_sec = np.convolve(
        np.pad(per_sec, (k, k), mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), mode="same"
    )[k:-k]
    t_sec = np.arange(n_samples) / sr
    return np.interp(t_sec, np.arange(len(per_sec)) + 0.5, per_sec).astype(np.float32)


def remix_attenuated(stems: dict[str, np.ndarray], gain: np.ndarray) -> np.ndarray:
    """Voix intactes + autres sources multipliées par ``gain`` (atténuées pendant la musique)."""
    rest = stems["drums"] + stems["bass"] + stems["other"]
    return stems["vocals"] + rest * gain[None, :]
