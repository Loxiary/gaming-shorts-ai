from datetime import UTC, datetime


def utcnow() -> datetime:
    """Horodatage UTC conscient du fuseau (toutes les dates sont stockées en UTC)."""
    return datetime.now(UTC)
