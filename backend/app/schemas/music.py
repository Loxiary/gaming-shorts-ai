from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.render.editorial import MUSIC_MOODS


def _strip(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class MusicTrackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    artist: str | None = Field(default=None, max_length=300)
    license: str | None = Field(default=None, max_length=300)
    source_url: str | None = Field(default=None, max_length=500)
    moods: list[str] = Field(default_factory=list, max_length=6)
    notes: str | None = Field(default=None, max_length=2000)
    license_confirmed: bool = False

    @field_validator("title", "artist", "license", "source_url", "notes")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return _strip(value)

    @field_validator("source_url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        if value and not value.lower().startswith(("http://", "https://")):
            raise ValueError("L'adresse de la source doit commencer par http:// ou https://")
        return value

    @field_validator("moods")
    @classmethod
    def _moods(cls, value: list[str]) -> list[str]:
        out = []
        for m in value:
            m = m.strip().lower()
            if m not in MUSIC_MOODS:
                raise ValueError(f"Ambiance inconnue « {m} ». Choix : {', '.join(MUSIC_MOODS)}")
            if m not in out:
                out.append(m)
        return out


class MusicTrackOut(BaseModel):
    id: str
    file_path: str
    file_name: str
    file_size_bytes: int | None
    duration_seconds: float | None
    title: str | None
    artist: str | None
    license: str | None
    source_url: str | None
    moods: list[str]
    notes: str | None
    license_confirmed: bool
    usable: bool
    audio_url: str


class MusicScanOut(BaseModel):
    added: int
    removed: int
    total: int
    errors: list[str]
    folder: str


class AudioAssetOut(BaseModel):
    id: str
    label: str
    purpose: str
    size_mb: float
    license: str
    credit: str | None
    present: bool
    is_voice: bool
    language: str | None


class AudioStatusOut(BaseModel):
    assets: list[AudioAssetOut]
    moods: list[str]
    music_folder: str
    download_command: str
