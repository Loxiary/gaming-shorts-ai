"""Contexte d'exécution transmis aux handlers d'étapes."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings

if TYPE_CHECKING:
    from app.adapters.registry import Adapters


@dataclass
class StepContext:
    job_id: str
    project_id: str
    kind: str
    step_name: str
    attempt: int
    settings: Settings
    session_factory: sessionmaker[Session]
    _adapters: Callable[[], Adapters]
    _progress: Callable[[float, str | None], None]
    _cancel_requested: Callable[[], bool]
    heartbeat: Callable[[], None]
    _last_progress: float = field(default=0.0)
    _last_cancel_check: float = field(default=0.0)

    @property
    def step_seconds(self) -> float:  # jobs de démonstration
        return self.settings.demo_step_seconds

    @property
    def adapters(self) -> Adapters:
        return self._adapters()

    def report_progress(self, fraction: float, detail: str | None = None) -> None:
        """Progression de l'étape (0..1). Écritures en base limitées à 2 par seconde."""
        now = time.monotonic()
        if fraction < 1.0 and now - self._last_progress < 0.5:
            return
        self._last_progress = now
        self._progress(max(0.0, min(fraction, 1.0)), detail)

    def check_cancel(self) -> None:
        """Point d'arrêt sûr : lève JobCancelled si l'utilisateur a demandé l'annulation."""
        from app.workers.errors import JobCancelled

        now = time.monotonic()
        if now - self._last_cancel_check < 1.0:
            return
        self._last_cancel_check = now
        if self._cancel_requested():
            raise JobCancelled()


StepHandler = Callable[[StepContext], "dict[str, Any] | None"]
