"""Exécution des étapes par type de job.

Phase 1 : uniquement des handlers de DÉMONSTRATION (simple attente). Aucun traitement réel.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


class DemoFailure(RuntimeError):
    """Échec volontaire du job de démonstration « demo_failure »."""


@dataclass
class StepContext:
    job_id: str
    kind: str
    step_name: str
    attempt: int
    step_seconds: float
    heartbeat: Callable[[], None]


StepHandler = Callable[[StepContext], None]


def _simulated_wait(ctx: StepContext) -> None:
    deadline = time.monotonic() + ctx.step_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.5, remaining))
        ctx.heartbeat()


def demo_step(ctx: StepContext) -> None:
    _simulated_wait(ctx)


def demo_failure_step(ctx: StepContext) -> None:
    _simulated_wait(ctx)
    if ctx.step_name == "demo_step_2" and ctx.attempt == 1:
        raise DemoFailure(
            "Échec simulé (démonstration) à l'étape 2 lors de la première tentative. "
            "Relancez le job : les étapes déjà terminées ne seront pas rejouées."
        )


HANDLERS: dict[str, StepHandler] = {
    "demo": demo_step,
    "demo_failure": demo_failure_step,
}
