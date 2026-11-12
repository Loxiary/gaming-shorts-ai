"""Bibliothèque musicale locale (Phase 5) : morceaux autorisés, avec licence renseignée."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base, UTCDateTime, new_id


class MusicTrack(Base):
    """Un morceau déposé par l'utilisateur dans GSA_DATA_DIR/music.

    Il n'est utilisable dans un short que si sa licence est renseignée ET que l'utilisateur a
    confirmé disposer de l'autorisation (``license_confirmed``). Aucune musique n'est
    téléchargée ni choisie hors de cette bibliothèque.
    """

    __tablename__ = "music_tracks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    title: Mapped[str | None] = mapped_column(String(300))
    artist: Mapped[str | None] = mapped_column(String(300))
    license: Mapped[str | None] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(500))
    moods: Mapped[str | None] = mapped_column(String(300))  # liste séparée par des virgules
    notes: Mapped[str | None] = mapped_column(Text)
    license_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    @property
    def usable(self) -> bool:
        return bool(self.license_confirmed and self.license and self.license.strip())

    @property
    def mood_list(self) -> list[str]:
        return [m.strip().lower() for m in (self.moods or "").split(",") if m.strip()]
