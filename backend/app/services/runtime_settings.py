"""Réglages globaux modifiables depuis l'interface (Phase 6).

Les valeurs du ``.env`` restent les valeurs de référence. L'interface peut en surcharger une
liste fermée (aucun chemin, port, clé ni secret) ; les surcharges sont stockées en base
(``app_settings``), validées avec les mêmes contraintes que le ``.env``, et appliquées par le
worker au début de chaque job. « Rétablir » supprime la surcharge.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.services.budget import get_setting, set_setting

OVERRIDES_KEY = "runtime_overrides"


@dataclass(frozen=True)
class RuntimeField:
    key: str
    label: str
    group: str
    help: str
    choices: tuple[str, ...] = ()


FIELDS: tuple[RuntimeField, ...] = (
    RuntimeField(
        "max_download_height",
        "Hauteur maximale téléchargée (px)",
        "Import",
        "Résolution maximale demandée à YouTube (360 à 2160). 1080 suffit pour un short.",
    ),
    RuntimeField(
        "max_source_minutes",
        "Durée maximale d'une source (min)",
        "Import",
        "Une vidéo plus longue est refusée à l'import (1 à 1440).",
    ),
    RuntimeField(
        "min_free_disk_gb",
        "Espace disque minimal (Go)",
        "Import",
        "Un téléchargement est refusé si l'espace libre passe sous ce seuil.",
    ),
    RuntimeField(
        "whisper_beam_size",
        "Précision de la transcription (beam)",
        "Transcription",
        "5 = précis (défaut) ; 1 = environ 2 fois plus rapide, un peu moins précis.",
    ),
    RuntimeField(
        "whisper_language",
        "Langue de transcription",
        "Transcription",
        "Vide = détection automatique ; sinon code à 2 lettres (fr, en…).",
    ),
    RuntimeField(
        "llm_effort",
        "Effort de l'IA",
        "IA",
        "Niveau de réflexion de Claude : plus élevé = plus de jetons de sortie (coût).",
        ("low", "medium", "high"),
    ),
    RuntimeField(
        "frames_per_candidate",
        "Images envoyées par extrait",
        "IA",
        "0 à 20. Chaque image coûte environ 0,003 $ ; 0 = texte seul.",
    ),
    RuntimeField(
        "analysis_proxy_height",
        "Résolution d'analyse (px)",
        "Analyse",
        "Copie basse définition utilisée pour l'analyse (240 à 1080).",
    ),
    RuntimeField(
        "render_x264_preset",
        "Vitesse d'encodage (libx264)",
        "Montage",
        "Plus rapide = fichier un peu plus gros à qualité égale.",
        ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"),
    ),
    RuntimeField(
        "retention_temp_days",
        "Fichiers intermédiaires (jours)",
        "Stockage",
        "Fichiers de travail régénérables (audio intermédiaire, images, copies d'analyse) "
        "proposés au nettoyage après ce délai. 0 = jamais.",
    ),
    RuntimeField(
        "retention_render_days",
        "Shorts non exportés (jours)",
        "Stockage",
        "Rendus jamais exportés proposés au nettoyage après ce délai. 0 = jamais.",
    ),
    RuntimeField(
        "retention_source_days",
        "Vidéos sources (jours)",
        "Stockage",
        "Vidéos sources non utilisées depuis ce délai proposées au nettoyage (transcription, "
        "analyses et rendus conservés). 0 = jamais.",
    ),
    RuntimeField(
        "retention_auto",
        "Nettoyage automatique des fichiers intermédiaires",
        "Stockage",
        "Si activé, le worker supprime chaque jour les fichiers intermédiaires échus. Les "
        "sources et les shorts ne sont jamais supprimés automatiquement.",
    ),
)
FIELD_KEYS = {f.key for f in FIELDS}


def _adapter(key: str) -> TypeAdapter[Any]:
    info = Settings.model_fields[key]
    if not info.metadata:
        return TypeAdapter(info.annotation)
    return TypeAdapter(Annotated[info.annotation, *info.metadata])  # type: ignore[name-defined]


def validate_value(key: str, value: Any) -> Any:
    if key not in FIELD_KEYS:
        raise AppError(f"Réglage non modifiable depuis l'interface : {key}")
    field = next(f for f in FIELDS if f.key == key)
    try:
        parsed = _adapter(key).validate_python(value)
    except ValidationError as exc:
        detail = exc.errors()[0].get("msg", "valeur invalide")
        raise AppError(f"{field.label} : {detail}") from exc
    if field.choices and parsed not in field.choices:
        raise AppError(f"{field.label} : choisir parmi {', '.join(field.choices)}")
    return parsed


def get_overrides(session: Session) -> dict[str, Any]:
    raw = get_setting(session, OVERRIDES_KEY, {})
    out: dict[str, Any] = {}
    for key, value in raw.items():
        try:
            out[key] = validate_value(key, value)
        except AppError:
            continue  # réglage devenu invalide (mise à jour) : ignoré, la valeur .env s'applique
    return out


def set_overrides(session: Session, changes: dict[str, Any]) -> dict[str, Any]:
    """``changes`` : {clé: valeur} ; valeur ``None`` = rétablir la valeur du .env."""
    current = get_overrides(session)
    for key, value in changes.items():
        if value is None:
            current.pop(key, None)
        else:
            current[key] = validate_value(key, value)
    set_setting(session, OVERRIDES_KEY, current)
    return current


def effective_settings(session: Session, base: Settings) -> Settings:
    overrides = get_overrides(session)
    return base.model_copy(update=overrides) if overrides else base


def describe(session: Session, base: Settings) -> list[dict[str, Any]]:
    overrides = get_overrides(session)
    out = []
    for f in FIELDS:
        info = Settings.model_fields[f.key]
        value = overrides.get(f.key, getattr(base, f.key))
        bounds = {
            k: getattr(m, k)
            for m in info.metadata
            for k in ("ge", "le", "gt", "lt")
            if getattr(m, k, None) is not None
        }
        kind = (
            "bool"
            if isinstance(value, bool)
            else "int"
            if isinstance(value, int)
            else "float"
            if isinstance(value, float)
            else "choice"
            if f.choices
            else "str"
        )
        out.append(
            {
                "key": f.key,
                "label": f.label,
                "group": f.group,
                "help": f.help,
                "type": kind,
                "choices": list(f.choices),
                "min": bounds.get("ge", bounds.get("gt")),
                "max": bounds.get("le", bounds.get("lt")),
                "value": value,
                "env_value": getattr(base, f.key),
                "overridden": f.key in overrides,
            }
        )
    return out


def overrides_fingerprint(session: Session) -> str:
    return json.dumps(get_overrides(session), sort_keys=True)
