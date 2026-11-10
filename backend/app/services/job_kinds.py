"""Catalogue des types de jobs connus.

Phase 1 : seuls des jobs de DÉMONSTRATION existent. Ils n'effectuent aucun téléchargement,
aucune analyse et aucun rendu ; ils simulent des étapes pour valider la file persistante.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StepDefinition:
    name: str
    label: str


@dataclass(frozen=True)
class JobKind:
    kind: str
    label: str
    description: str
    is_demo: bool
    steps: tuple[StepDefinition, ...]


_DEMO_STEPS = (
    StepDefinition("demo_prepare", "Préparation (simulation)"),
    StepDefinition("demo_step_1", "Étape simulée 1"),
    StepDefinition("demo_step_2", "Étape simulée 2"),
    StepDefinition("demo_finalize", "Finalisation (simulation)"),
)

JOB_KINDS: dict[str, JobKind] = {
    "demo": JobKind(
        kind="demo",
        label="Démonstration",
        description=(
            "Job de démonstration : simule quatre étapes (attente) pour tester la file "
            "d'attente. Aucun traitement vidéo ou IA n'est effectué."
        ),
        is_demo=True,
        steps=_DEMO_STEPS,
    ),
    "demo_failure": JobKind(
        kind="demo_failure",
        label="Démonstration — échec puis reprise",
        description=(
            "Job de démonstration qui échoue volontairement à l'étape 2 lors de la première "
            "tentative, pour tester la relance à partir de la dernière étape valide. "
            "Aucun traitement vidéo ou IA n'est effectué."
        ),
        is_demo=True,
        steps=_DEMO_STEPS,
    ),
}


def get_job_kind(kind: str) -> JobKind | None:
    return JOB_KINDS.get(kind)
