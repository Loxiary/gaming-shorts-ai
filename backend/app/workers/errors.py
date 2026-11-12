"""Exceptions de contrôle du pipeline."""


class StepError(Exception):
    """Échec d'étape attendu, avec un message compréhensible par l'utilisateur."""

    def __init__(self, message: str, *, technical: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.technical = technical


class JobCancelled(Exception):
    """Annulation demandée par l'utilisateur, détectée à un point d'arrêt sûr."""
