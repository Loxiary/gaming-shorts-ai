"""Registre des handlers par type de job.

- ``demo`` / ``demo_failure`` : jobs de DÉMONSTRATION (simple attente, aucun traitement réel).
- ``ingest_youtube`` : import réel (validation, téléchargement, ffprobe, audio, transcription).
"""

from __future__ import annotations

import time
from typing import Any

from app.workers.context import StepContext, StepHandler


class DemoFailure(RuntimeError):
    """Échec volontaire du job de démonstration « demo_failure »."""


def _simulated_wait(ctx: StepContext) -> None:
    deadline = time.monotonic() + ctx.step_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.5, remaining))
        ctx.heartbeat()


def demo_step(ctx: StepContext) -> dict[str, Any] | None:
    _simulated_wait(ctx)
    return None


def demo_failure_step(ctx: StepContext) -> dict[str, Any] | None:
    _simulated_wait(ctx)
    if ctx.step_name == "demo_step_2" and ctx.attempt == 1:
        raise DemoFailure(
            "Échec simulé (démonstration) à l'étape 2 lors de la première tentative. "
            "Relancez le job : les étapes déjà terminées ne seront pas rejouées."
        )
    return None


def ingest_step(ctx: StepContext) -> dict[str, Any] | None:
    from app.workers.pipeline.ingest import INGEST_STEPS

    return INGEST_STEPS[ctx.step_name](ctx)


def analyze_step(ctx: StepContext) -> dict[str, Any] | None:
    from app.workers.pipeline.analyze import ANALYZE_STEPS

    return ANALYZE_STEPS[ctx.step_name](ctx)


def render_step(ctx: StepContext) -> dict[str, Any] | None:
    from app.workers.pipeline.render import RENDER_STEPS

    return RENDER_STEPS[ctx.step_name](ctx)


HANDLERS: dict[str, StepHandler] = {
    "render_clip": render_step,
    "analyze_clips": analyze_step,
    "demo": demo_step,
    "demo_failure": demo_failure_step,
    "ingest_youtube": ingest_step,
}
