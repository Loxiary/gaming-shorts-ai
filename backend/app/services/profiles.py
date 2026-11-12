"""Profils de montage : CRUD, duplication et profils initiaux du cahier des charges (§12)."""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import CRITERIA, EditingProfile  # noqa: F401 (réexporté pour renders)
from app.render.style import normalize_subtitle_style
from app.schemas.analysis import ProfileIn, ProfileOut

logger = logging.getLogger(__name__)


def _w(**overrides: float) -> dict[str, float]:
    weights = dict.fromkeys(CRITERIA, 1.0)
    weights.update(overrides)
    return weights


DEFAULT_PROFILES = [
    {
        "name": "GTA 6 — Viral",
        "description": "Moments forts au potentiel de partage maximal.",
        "editorial_focus": "Privilégier les moments surprenants ou spectaculaires, avec une "
        "accroche immédiate dans les premières secondes et une chute nette.",
        "threshold": 55.0,
        "weights": _w(hook=1.6, retention=1.5, entertainment=1.3, av_quality=0.7, narrative=0.8),
        "is_default": True,
    },
    {
        "name": "GTA 6 — Humour",
        "description": "Situations drôles, réactions, échecs comiques.",
        "editorial_focus": "Privilégier l'humour : réactions spontanées, échecs comiques, "
        "situations absurdes. La chute doit être comprise sans contexte.",
        "threshold": 50.0,
        "weights": _w(entertainment=1.6, standalone=1.3, hook=1.2, av_quality=0.7),
    },
    {
        "name": "GTA 6 — Action",
        "description": "Poursuites, fusillades, cascades.",
        "editorial_focus": "Privilégier l'intensité : poursuites, combats, cascades, "
        "retournements de situation. Le rythme compte plus que les dialogues.",
        "threshold": 50.0,
        "weights": _w(entertainment=1.6, av_quality=1.2, hook=1.2, narrative=0.8),
    },
    {
        "name": "Gaming — Immersion",
        "description": "Ambiance, beauté du jeu, exploration.",
        "editorial_focus": "Privilégier l'ambiance et la qualité visuelle : panoramas, "
        "atmosphère, moments contemplatifs qui donnent envie de jouer.",
        "threshold": 50.0,
        "weights": _w(av_quality=1.6, originality=1.2, narrative=1.0, hook=0.8, entertainment=0.8),
    },
    {
        "name": "Gaming — Histoire",
        "description": "Séquences narratives compréhensibles seules.",
        "editorial_focus": "Privilégier les séquences avec un début, un développement et une "
        "fin : mini-récits, missions, rebondissements compréhensibles sans contexte.",
        "threshold": 50.0,
        "weights": _w(narrative=1.7, standalone=1.5, hook=1.0, entertainment=0.9),
    },
]


def ensure_default_profiles(session: Session) -> None:
    """Crée les profils d'exemple si aucun profil n'existe (idempotent)."""
    if session.scalar(select(func.count()).select_from(EditingProfile)):
        return
    for data in DEFAULT_PROFILES:
        session.add(
            EditingProfile(
                name=data["name"],
                description=data["description"],
                editorial_focus=data["editorial_focus"],
                threshold=data["threshold"],
                weights_json=json.dumps(data["weights"]),
                is_default=data.get("is_default", False),
            )
        )
    session.commit()
    logger.info("Profils de montage initiaux créés")


def to_out(profile: EditingProfile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        editorial_focus=profile.editorial_focus,
        threshold=profile.threshold,
        weights=json.loads(profile.weights_json),
        output_language=profile.output_language,
        min_duration=profile.min_duration,
        max_duration=profile.max_duration,
        max_candidates=profile.max_candidates,
        use_vision=profile.use_vision,
        is_default=profile.is_default,
        subtitle_mode=profile.subtitle_mode,
        subtitle_style=normalize_subtitle_style(
            json.loads(profile.subtitle_style_json) if profile.subtitle_style_json else None
        ),
        layout=profile.layout,
        zoom_intensity=profile.zoom_intensity,
        hook_enabled=profile.hook_enabled,
        cta_enabled=profile.cta_enabled,
        cta_text=profile.cta_text,
        render_encoder=profile.render_encoder,
        narration_mode=profile.narration_mode,
        narration_voice=profile.narration_voice,
        narration_speed=profile.narration_speed,
        narration_level_db=profile.narration_level_db,
        game_level_db=profile.game_level_db,
        music_mode=profile.music_mode,
        music_level_db=profile.music_level_db,
        source_music_mode=profile.source_music_mode,
        source_music_reduction_db=profile.source_music_reduction_db,
        facecam_mode=profile.facecam_mode,
        censor_profanity=profile.censor_profanity,
        min_confidence=profile.min_confidence,
        narration_title=profile.narration_title,
        react_overlay=profile.react_overlay,
        bleep_profanity=profile.bleep_profanity,
        effects_mode=profile.effects_mode,
        transition_in=profile.transition_in,
        transition_out=profile.transition_out,
        sfx_mode=profile.sfx_mode,
        sfx_level_db=profile.sfx_level_db,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def snapshot(profile: EditingProfile) -> dict[str, object]:
    return to_out(profile).model_dump(mode="json")


def list_profiles(session: Session) -> list[EditingProfile]:
    return list(
        session.scalars(
            select(EditingProfile).order_by(EditingProfile.is_default.desc(), EditingProfile.name)
        )
    )


def get_profile(session: Session, profile_id: str) -> EditingProfile:
    profile = session.get(EditingProfile, profile_id)
    if profile is None:
        raise NotFoundError(f"Profil introuvable : {profile_id}")
    return profile


def default_profile(session: Session) -> EditingProfile:
    profile = session.scalar(select(EditingProfile).where(EditingProfile.is_default.is_(True)))
    profile = profile or session.scalar(select(EditingProfile).order_by(EditingProfile.name))
    if profile is None:
        raise AppError("Aucun profil de montage : créez-en un dans « Profils ».")
    return profile


def _apply(profile: EditingProfile, data: ProfileIn) -> None:
    profile.name = data.name
    profile.description = data.description
    profile.editorial_focus = data.editorial_focus
    profile.threshold = data.threshold
    profile.weights_json = json.dumps(data.weights)
    profile.output_language = data.output_language
    profile.min_duration = data.min_duration
    profile.max_duration = data.max_duration
    profile.max_candidates = data.max_candidates
    profile.use_vision = data.use_vision
    profile.subtitle_mode = data.subtitle_mode
    profile.subtitle_style_json = json.dumps(data.subtitle_style)
    profile.layout = data.layout
    profile.zoom_intensity = data.zoom_intensity
    profile.hook_enabled = data.hook_enabled
    profile.cta_enabled = data.cta_enabled
    profile.cta_text = data.cta_text
    profile.render_encoder = data.render_encoder
    profile.narration_mode = data.narration_mode
    profile.narration_voice = data.narration_voice
    profile.narration_speed = data.narration_speed
    profile.narration_level_db = data.narration_level_db
    profile.game_level_db = data.game_level_db
    profile.music_mode = data.music_mode
    profile.music_level_db = data.music_level_db
    profile.source_music_mode = data.source_music_mode
    profile.source_music_reduction_db = data.source_music_reduction_db
    profile.facecam_mode = data.facecam_mode
    profile.censor_profanity = data.censor_profanity
    profile.min_confidence = data.min_confidence
    profile.narration_title = data.narration_title
    profile.react_overlay = data.react_overlay
    profile.bleep_profanity = data.bleep_profanity
    profile.effects_mode = data.effects_mode
    profile.transition_in = data.transition_in
    profile.transition_out = data.transition_out
    profile.sfx_mode = data.sfx_mode
    profile.sfx_level_db = data.sfx_level_db


def _commit(session: Session, profile: EditingProfile, make_default: bool) -> EditingProfile:
    if make_default:
        for other in session.scalars(select(EditingProfile).where(EditingProfile.id != profile.id)):
            other.is_default = False
        profile.is_default = True
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(f"Un profil nommé « {profile.name} » existe déjà.") from exc
    return profile


def create_profile(session: Session, data: ProfileIn) -> EditingProfile:
    profile = EditingProfile()
    _apply(profile, data)
    session.add(profile)
    return _commit(session, profile, data.is_default)


def update_profile(session: Session, profile_id: str, data: ProfileIn) -> EditingProfile:
    profile = get_profile(session, profile_id)
    _apply(profile, data)
    return _commit(session, profile, data.is_default)


def duplicate_profile(session: Session, profile_id: str) -> EditingProfile:
    source = get_profile(session, profile_id)
    base = f"{source.name} (copie)"
    name, n = base, 2
    while session.scalar(select(EditingProfile.id).where(EditingProfile.name == name)):
        name, n = f"{base} {n}", n + 1
    fields = to_out(source).model_dump(exclude={"id", "created_at", "updated_at"})
    data = ProfileIn.model_validate(fields | {"name": name[:120]})
    data.is_default = False
    return create_profile(session, data)


def delete_profile(session: Session, profile_id: str) -> None:
    profile = get_profile(session, profile_id)
    if profile.is_default:
        raise ConflictError(
            "Le profil par défaut ne peut pas être supprimé : choisissez-en un autre."
        )
    # Les analyses passées gardent leur instantané du profil (profile_id passe à NULL).
    session.delete(profile)
    session.commit()
