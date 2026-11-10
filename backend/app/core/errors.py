"""Erreurs métier explicites, converties en réponses JSON ``{"error": {"code", "message"}}``."""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class DatabaseNotReadyError(AppError):
    status_code = 503
    code = "database_not_ready"
