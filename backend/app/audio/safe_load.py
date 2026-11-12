"""Chargement SÛR des poids PyTorch téléchargés (``weights_only=True``).

Aucun code contenu dans un fichier téléchargé n'est exécuté : seuls des tenseurs, des
structures de données et une liste fermée de types sont acceptés (types de données numpy,
``fractions.Fraction`` et la classe ``HTDemucs`` du paquet demucs INSTALLÉ, référencée par
le paquet de poids mais jamais exécutée depuis le fichier).
"""

from __future__ import annotations

import fractions
from pathlib import Path
from typing import Any

import numpy as np
import torch
from numpy._core.multiarray import _reconstruct, scalar


def _numpy_data_types() -> list[Any]:
    dtypes = [
        type(np.dtype(t)) for t in ("float16", "float32", "float64", "int32", "int64", "bool")
    ]
    return [
        (_reconstruct, "numpy.core.multiarray._reconstruct"),
        (scalar, "numpy.core.multiarray.scalar"),
        (np.dtype, "numpy.dtype"),
        np.ndarray,
        *dtypes,
    ]


def safe_torch_load(path: Path, extra: list[Any] | None = None) -> Any:
    allowed = _numpy_data_types() + [fractions.Fraction] + list(extra or [])
    with torch.serialization.safe_globals(allowed):
        return torch.load(str(path), map_location="cpu", weights_only=True)
