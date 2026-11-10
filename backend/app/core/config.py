"""Configuration centralisée, chargée depuis les variables d'environnement et le fichier .env.

Toutes les variables sont préfixées par ``GSA_`` (voir ``.env.example`` à la racine du dépôt).
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "Gaming Shorts AI"
APP_VERSION = "0.1.0"
APP_PHASE = "Phase 1 — fondations"

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

DATA_SUBDIRS = ("sources", "temp", "projects", "exports", "logs")
DB_FILENAME = "gaming_shorts.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GSA_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=REPO_ROOT / "data")
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    log_level: str = "INFO"
    worker_poll_seconds: float = Field(default=1.0, gt=0, le=60)
    worker_stale_seconds: float = Field(default=30.0, ge=5, le=3600)
    demo_step_seconds: float = Field(default=2.0, ge=0, le=60)

    @field_validator("data_dir")
    @classmethod
    def _absolute_data_dir(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.is_absolute():
            value = (REPO_ROOT / value).resolve()
        return value

    @field_validator("api_host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        # Sécurité : l'application n'écoute que sur la boucle locale (cf. architecture §12).
        if value != "localhost" and not ipaddress.ip_address(value).is_loopback:
            raise ValueError(
                "GSA_API_HOST doit être une adresse de boucle locale (127.0.0.1) : "
                "l'exposition réseau n'est pas prise en charge."
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("GSA_LOG_LEVEL doit valoir DEBUG, INFO, WARNING ou ERROR")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    def subdir(self, name: str) -> Path:
        if name not in DATA_SUBDIRS:
            raise ValueError(f"Sous-dossier de données inconnu : {name}")
        return self.data_dir / name

    def ensure_data_dirs(self) -> None:
        """Crée le dossier data et ses sous-dossiers (vides) s'ils n'existent pas."""
        for name in DATA_SUBDIRS:
            self.subdir(name).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
