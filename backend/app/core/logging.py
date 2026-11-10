"""Journalisation structurée (JSON) vers la console et ``data/logs/<composant>.log``."""

from __future__ import annotations

import io
import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime

from app.core.config import Settings

# Champs de contexte acceptés via ``logger.info(..., extra={...})``.
CONTEXT_FIELDS = ("project_id", "job_id", "step", "worker_id", "kind", "status")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings, component: str) -> None:
    """Configure le logger racine. ``component`` vaut ``api`` ou ``worker``."""
    settings.ensure_data_dirs()
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    for handler in list(root.handlers):
        if getattr(handler, "_gsa", False):
            root.removeHandler(handler)
            handler.close()

    formatter = JsonFormatter()
    # stdout en UTF-8 : évite les erreurs d'encodage (cp1252) quand la sortie est redirigée
    # vers un fichier par scripts\start.ps1, et les faux « NativeCommandError » de PowerShell.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    file_handler = logging.handlers.RotatingFileHandler(
        settings.subdir("logs") / f"{component}.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    for handler in (console, file_handler):
        handler._gsa = True  # type: ignore[attr-defined]
        root.addHandler(handler)
