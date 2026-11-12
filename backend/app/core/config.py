"""Configuration centralisée, chargée depuis les variables d'environnement et le fichier .env.

Toutes les variables sont préfixées par ``GSA_`` (voir ``.env.example`` à la racine du dépôt).
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "Gaming Shorts AI"
APP_VERSION = "0.9.0"
APP_PHASE = "Phase 9 — facecam réaction"

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

DATA_SUBDIRS = ("sources", "temp", "projects", "exports", "logs", "models", "music", "backups")
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

    # --- Import / téléchargement (Phase 2)
    max_download_height: int = Field(default=1080, ge=360, le=2160)
    max_source_minutes: int = Field(default=240, ge=1, le=1440)
    min_free_disk_gb: float = Field(default=5.0, ge=0, le=1000)
    ytdlp_js_runtime: str = "node"

    # --- Transcription locale faster-whisper (Phase 2)
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"  # auto | cuda | cpu
    whisper_compute_type: str = "auto"  # auto | int8_float16 | float16 | int8 | float32
    whisper_language: str = Field(default="", pattern="^([a-z]{2})?$")  # vide = auto
    whisper_vad: bool = True
    whisper_beam_size: int = Field(default=5, ge=1, le=10)

    # --- Analyse des clips (Phase 3)
    # Clé lue depuis .env ou l'environnement (ANTHROPIC_API_KEY, sans préfixe GSA_).
    # Jamais journalisée ni renvoyée par l'API.
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "GSA_ANTHROPIC_API_KEY")
    )
    llm_model: str = "claude-sonnet-5-5"
    llm_effort: str = Field(default="medium", pattern="^(low|medium|high)$")
    # Tarifs en $ par million de jetons (à mettre à jour si Anthropic change ses prix).
    llm_price_input_per_mtok: float = Field(default=2.0, ge=0)
    llm_price_output_per_mtok: float = Field(default=10.0, ge=0)
    llm_price_cache_read_per_mtok: float = Field(default=0.10, ge=0)
    llm_price_cache_write_per_mtok: float = Field(default=2.50, ge=0)
    default_monthly_cap_usd: float = Field(default=40.0, ge=0)
    analysis_proxy_height: int = Field(default=480, ge=240, le=1080)
    frames_per_candidate: int = Field(default=8, ge=0, le=20)

    # --- Montage (Phase 4)
    render_x264_preset: str = Field(
        default="faster", pattern="^(ultrafast|superfast|veryfast|faster|fast|medium|slow)$"
    )

    # --- Facecam « réaction » incrustée (Phase 9) : même vidéo pour tous les shorts, en boucle,
    # sans son, en bas à gauche, dans un cercle à contour jaune. Chemin relatif à data_dir.
    react_video: str = "facecam/facerig_cam.mp4"
    react_center_x: float = Field(default=0.43, ge=0, le=1)  # centre du visage (fraction)
    react_center_y: float = Field(default=0.50, ge=0, le=1)
    react_zoom: float = Field(default=1.0, ge=0.2, le=1)  # côté du carré / hauteur vidéo
    react_diameter: int = Field(default=360, ge=160, le=600)  # pixels dans le short 1080×1920

    # --- Stockage (Phase 6). Délais en jours, 0 = jamais. Modifiables dans Paramètres.
    retention_temp_days: int = Field(default=7, ge=0, le=3650)
    retention_render_days: int = Field(default=0, ge=0, le=3650)
    retention_source_days: int = Field(default=0, ge=0, le=3650)
    retention_auto: bool = False  # nettoyage quotidien des seuls fichiers intermédiaires

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

    @field_validator("whisper_device")
    @classmethod
    def _valid_device(cls, value: str) -> str:
        value = value.lower()
        if value not in {"auto", "cuda", "cpu"}:
            raise ValueError("GSA_WHISPER_DEVICE doit valoir auto, cuda ou cpu")
        return value

    @field_validator("whisper_language")
    @classmethod
    def _valid_language(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not (value.isalpha() and 2 <= len(value) <= 3):
            raise ValueError("GSA_WHISPER_LANGUAGE doit être un code langue (ex. fr, en) ou vide")
        return value

    @field_validator("llm_effort")
    @classmethod
    def _valid_effort(cls, value: str) -> str:
        value = value.lower()
        if value not in {"low", "medium", "high"}:
            raise ValueError("GSA_LLM_EFFORT doit valoir low, medium ou high")
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

    @property
    def whisper_model_dir(self) -> Path:
        return self.subdir("models") / f"faster-whisper-{self.whisper_model}"

    def to_relative(self, path: Path) -> str:
        """Chemin stocké en base : relatif à la racine data, séparateurs « / »."""
        return path.resolve().relative_to(self.data_dir.resolve()).as_posix()

    def resolve_data_path(self, relative: str) -> Path:
        """Résout un chemin relatif stocké en base en refusant toute sortie de la racine data."""
        root = self.data_dir.resolve()
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"Chemin hors du dossier de données refusé : {relative}")
        return candidate

    def ensure_data_dirs(self) -> None:
        """Crée le dossier data et ses sous-dossiers (vides) s'ils n'existent pas."""
        for name in DATA_SUBDIRS:
            self.subdir(name).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
