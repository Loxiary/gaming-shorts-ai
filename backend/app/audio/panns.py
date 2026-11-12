"""Détection de musique et de parole : PANNs CNN14 (16 kHz, 527 classes AudioSet).

Architecture reproduite d'après le code de référence MIT (Kong et al., « PANNs: Large-Scale
Pretrained Audio Neural Networks », 2020). Le prétraitement (STFT et banc mel) utilise les
poids fournis dans le checkpoint, sans dépendance à librosa. Le classifieur donne une
probabilité par fenêtre de 2 s, avancée d'1 s : c'est une ESTIMATION (musique d'ambiance,
jingles ou bruitages musicaux peuvent être confondus).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from app.audio.safe_load import safe_torch_load

SAMPLE_RATE = 16_000
N_FFT, HOP = 512, 160
SPEECH, MUSIC = 0, 137  # indices AudioSet « Speech » et « Music »
SINGING = 27


class _ConvBlock(nn.Module):
    def __init__(self, cin: int, cout: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(cin, cout, 3, 1, 1, bias=False)
        self.conv2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
        self.bn1 = nn.BatchNorm2d(cout)
        self.bn2 = nn.BatchNorm2d(cout)

    def forward(self, x: torch.Tensor, pool: tuple[int, int]) -> torch.Tensor:
        x = F.relu_(self.bn1(self.conv1(x)))
        x = F.relu_(self.bn2(self.conv2(x)))
        return F.avg_pool2d(x, kernel_size=pool)


class _Stft(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv_real = nn.Conv1d(1, N_FFT // 2 + 1, N_FFT, HOP, bias=False)
        self.conv_imag = nn.Conv1d(1, N_FFT // 2 + 1, N_FFT, HOP, bias=False)


class _Spectrogram(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.stft = _Stft()

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # (B, samples) -> (B, 1, T, F)
        x = F.pad(x[:, None, :], (N_FFT // 2, N_FFT // 2), mode="reflect")
        real, imag = self.stft.conv_real(x), self.stft.conv_imag(x)
        return (real**2 + imag**2).transpose(1, 2)[:, None]


class _LogMel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.melW = nn.Parameter(torch.zeros(N_FFT // 2 + 1, 64), requires_grad=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        mel = torch.matmul(x, self.melW)
        return 10.0 * torch.log10(torch.clamp(mel, min=1e-10))


class Cnn14(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.spectrogram_extractor = _Spectrogram()
        self.logmel_extractor = _LogMel()
        self.bn0 = nn.BatchNorm2d(64)
        chans = [1, 64, 128, 256, 512, 1024, 2048]
        for i in range(6):
            setattr(self, f"conv_block{i + 1}", _ConvBlock(chans[i], chans[i + 1]))
        self.fc1 = nn.Linear(2048, 2048)
        self.fc_audioset = nn.Linear(2048, 527)

    def forward(self, wave: torch.Tensor) -> torch.Tensor:
        x = self.logmel_extractor(self.spectrogram_extractor(wave))  # (B, 1, T, 64)
        x = self.bn0(x.transpose(1, 3)).transpose(1, 3)
        for i in range(1, 7):
            x = getattr(self, f"conv_block{i}")(x, (1, 1) if i == 6 else (2, 2))
        x = torch.mean(x, dim=3)
        x = F.max_pool1d(x, 3, 1, 1) + F.avg_pool1d(x, 3, 1, 1)
        x = torch.max(x, dim=2).values + torch.mean(x, dim=2)
        x = F.relu_(self.fc1(x))
        return torch.sigmoid(self.fc_audioset(x))


@dataclass
class AudioTags:
    """Probabilités par seconde (fenêtre centrée sur la seconde)."""

    music: list[float]
    speech: list[float]
    singing: list[float]

    def music_seconds(self, threshold: float) -> int:
        return sum(1 for p in self.music if p >= threshold)


class MusicDetector:
    def __init__(self, checkpoint: Path) -> None:
        if not checkpoint.is_file():
            raise FileNotFoundError(
                f"Modèle de détection de musique absent ({checkpoint}). Téléchargez-le : "
                "python -m app.cli.models download cnn14-16k"
            )
        self.model = Cnn14()
        state = safe_torch_load(checkpoint)["model"]
        self.model.load_state_dict(state, strict=True)
        self.model.eval()

    @torch.inference_mode()
    def tag(self, audio: np.ndarray, window_s: float = 2.0, batch: int = 32) -> AudioTags:
        """``audio`` : mono float32, 16 kHz. Une prédiction par seconde."""
        n_sec = max(1, int(np.ceil(len(audio) / SAMPLE_RATE)))
        win = int(window_s * SAMPLE_RATE)
        padded = np.pad(audio.astype(np.float32), (win // 2, win))
        starts = [i * SAMPLE_RATE for i in range(n_sec)]
        probs: list[np.ndarray] = []
        for b in range(0, len(starts), batch):
            chunk = np.stack([padded[s : s + win] for s in starts[b : b + batch]])
            probs.append(self.model(torch.from_numpy(chunk)).numpy())
        p = np.concatenate(probs)
        return AudioTags(
            music=p[:, MUSIC].round(4).tolist(),
            speech=p[:, SPEECH].round(4).tolist(),
            singing=p[:, SINGING].round(4).tolist(),
        )
