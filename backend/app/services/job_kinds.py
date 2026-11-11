"""Catalogue des types de jobs connus.

- ``ingest_youtube`` : traitement réel (Phase 2), créé par l'import d'un lien.
- ``demo`` / ``demo_failure`` : jobs de DÉMONSTRATION (simple attente, aucun traitement),
  conservés pour tester la file d'attente.
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

INGEST_STEPS = (
    StepDefinition("validating_source", "Validation de la source"),
    StepDefinition("downloading", "Téléchargement"),
    StepDefinition("probing_media", "Analyse technique (ffprobe)"),
    StepDefinition("extracting_audio", "Extraction de l'audio"),
    StepDefinition("transcribing", "Transcription (faster-whisper)"),
)

ANALYZE_STEPS = (
    StepDefinition("preparing_proxy", "Préparation de l'analyse (copie légère)"),
    StepDefinition("detecting_scenes", "Détection des changements de scène"),
    StepDefinition("analyzing_audio", "Analyse des signaux audio et de parole"),
    StepDefinition("generating_candidates", "Proposition d'extraits (61–180 s)"),
    StepDefinition("sampling_frames", "Extraction d'images horodatées"),
    StepDefinition("scoring_candidates", "Évaluation des extraits"),
    StepDefinition("selecting_clips", "Sélection (seuil, doublons)"),
)

RENDER_STEPS = (
    StepDefinition(
        "creating_editorial_plan", "Plan éditorial (accroche, appel à l'action, zooms, narration)"
    ),
    StepDefinition("detecting_facecam", "Détection du facecam"),
    StepDefinition("preparing_audio", "Audio : musique d'origine, narration, musique, mixage"),
    StepDefinition("preparing_subtitles", "Sous-titres (traduction si demandée)"),
    StepDefinition("rendering", "Rendu vertical 1080×1920"),
    StepDefinition("quality_check", "Contrôle qualité du fichier"),
    StepDefinition("building_risk_report", "Rapport de risques"),
)

JOB_KINDS: dict[str, JobKind] = {
    "render_clip": JobKind(
        kind="render_clip",
        label="Montage du short",
        description=(
            "Prépare le plan éditorial, détecte le facecam, traite l'audio (musique "
            "d'origine, narration, musique ajoutée), les sous-titres animés, rend le short, "
            "contrôle le fichier produit et établit le rapport de risques. L'export reste "
            "soumis à votre confirmation."
        ),
        is_demo=False,
        steps=RENDER_STEPS,
    ),
    "analyze_clips": JobKind(
        kind="analyze_clips",
        label="Analyse et détection des clips",
        description=(
            "Détecte les moments forts (scènes, audio, parole), propose des extraits de "
            "61 à 180 s, les fait évaluer (IA ou signaux seuls) et sélectionne ceux qui "
            "dépassent le seuil du profil."
        ),
        is_demo=False,
        steps=ANALYZE_STEPS,
    ),
    "ingest_youtube": JobKind(
        kind="ingest_youtube",
        label="Import YouTube et transcription",
        description=(
            "Vérifie la vidéo, la télécharge (yt-dlp), l'analyse (ffprobe), extrait l'audio "
            "et produit la transcription source horodatée (faster-whisper, en local)."
        ),
        is_demo=False,
        steps=INGEST_STEPS,
    ),
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
