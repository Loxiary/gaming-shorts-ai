"""Entités de la Phase 4 : rendus de shorts (plan éditorial, sous-titres, QC, risques, export)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base, UTCDateTime, new_id


class ClipRender(Base):
    """Un montage vertical d'un extrait candidat (plusieurs rendus possibles par extrait)."""

    __tablename__ = "clip_renders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("clip_candidates.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    # Instantané : bornes, profil et textes au moment de la demande (reproductible).
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    profile_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Public visé : « fr » ou « en » (titre, voix, sous-titres, publication dans cette langue).
    audience_language: Mapped[str | None] = mapped_column(String(5))
    candidate_snapshot_json: Mapped[str | None] = mapped_column(Text)

    # Plan éditorial : accroche, appel à l'action, mots clés, zooms (IA ou repli).
    plan_json: Mapped[str | None] = mapped_column(Text)
    plan_engine: Mapped[str | None] = mapped_column(String(20))  # llm | fallback
    # Sous-titres affichés : [{start, end, text, words:[...]}] + langue et nature.
    subtitles_json: Mapped[str | None] = mapped_column(Text)
    subtitle_language: Mapped[str | None] = mapped_column(String(10))
    subtitles_are_translation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    output_path: Mapped[str | None] = mapped_column(String(500))
    output_size_bytes: Mapped[int | None] = mapped_column()
    qc_json: Mapped[str | None] = mapped_column(Text)
    qc_passed: Mapped[bool | None] = mapped_column(Boolean)
    risk_report_json: Mapped[str | None] = mapped_column(Text)
    # Phase 5 : audio (détection/atténuation de musique, narration, musique ajoutée), facecam.
    audio_report_json: Mapped[str | None] = mapped_column(Text)
    facecam_json: Mapped[str | None] = mapped_column(Text)
    credits_json: Mapped[str | None] = mapped_column(Text)
    # Textes de publication (TikTok, YouTube) et musique conseillée à l'upload.
    publication_json: Mapped[str | None] = mapped_column(Text)
    preview_audio_path: Mapped[str | None] = mapped_column(String(500))
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Phase 6 : fichiers supprimés par le nettoyage (la fiche et les rapports restent).
    files_purged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    # Export : uniquement après confirmation explicite de l'utilisateur.
    export_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_exported")
    exported_path: Mapped[str | None] = mapped_column(String(500))
    export_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_warnings_json: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
