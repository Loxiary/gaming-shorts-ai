"""Plan éditorial d'un short (accroche, appel à l'action, mots clés, zooms) et traduction.

Règles du cahier des charges (§9 à §11) transmises à l'IA et vérifiées par le code :
- l'accroche ne promet aucun événement absent ; une citation doit être réellement prononcée ;
- les mots clés à colorer existent dans les sous-titres affichés ;
- les zooms tombent dans l'extrait ;
- la traduction est stockée à part et signalée comme telle, la transcription source
  n'est jamais modifiée.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

MAX_HOOK_CHARS = 60
MAX_CTA_CHARS = 70
MAX_ZOOMS = 3

LANG_NAMES = {
    "fr": "français",
    "en": "anglais",
    "es": "espagnol",
    "de": "allemand",
    "it": "italien",
    "pt": "portugais",
}


# --------------------------------------------------------------------------- schémas IA


class ZoomMoment(BaseModel):
    t: float  # secondes depuis le début du short
    duration: float
    reason: str


class EditorialPlan(BaseModel):
    hook_text: str
    hook_kind: Literal["quote", "original"]
    hook_reason: str
    cta_text: str
    keywords: list[str]
    zooms: list[ZoomMoment]
    warnings: list[str]


class TranslatedSentence(BaseModel):
    index: int
    text: str


class Translation(BaseModel):
    sentences: list[TranslatedSentence]


# --------------------------------------------------------------------------- données


@dataclass
class Sentence:
    start: float  # relatif au début du short
    end: float
    text: str
    words: list[tuple[float, float, str]] = field(default_factory=list)


def normalize_word(word: str) -> str:
    return re.sub(r"[^\w'’-]", "", word.lower(), flags=re.UNICODE).strip("'’-")


def validate_plan(
    plan: EditorialPlan, sentences: list[Sentence], duration: float, hook_enabled: bool
) -> EditorialPlan:
    """Contrôles stricts ; lève ValueError si l'IA n'a pas respecté les consignes."""
    if hook_enabled:
        if not plan.hook_text.strip() or len(plan.hook_text) > MAX_HOOK_CHARS:
            raise ValueError(f"accroche vide ou de plus de {MAX_HOOK_CHARS} caractères")
        if plan.hook_kind == "quote":
            spoken = normalize_text(" ".join(s.text for s in sentences))
            if normalize_text(plan.hook_text) not in spoken:
                raise ValueError(
                    "l'accroche « citation » n'est pas une phrase réellement prononcée"
                )
    if len(plan.cta_text) > MAX_CTA_CHARS:
        raise ValueError(f"appel à l'action de plus de {MAX_CTA_CHARS} caractères")
    if len(plan.zooms) > MAX_ZOOMS:
        raise ValueError(f"plus de {MAX_ZOOMS} zooms")
    for z in plan.zooms:
        if not (z.t >= 0 and z.t + z.duration <= duration and 0.5 <= z.duration <= 4):
            raise ValueError(f"zoom hors de l'extrait ou de durée invalide (t={z.t})")
    return plan


def normalize_text(text: str) -> str:
    return " ".join(normalize_word(w) for w in text.split() if normalize_word(w))


def filter_keywords(keywords: list[str], displayed_words: list[str]) -> list[str]:
    """Garde uniquement les mots clés présents dans les sous-titres affichés (max 12)."""
    present = {normalize_word(w) for w in displayed_words}
    out: list[str] = []
    for k in keywords:
        for part in k.split():
            n = normalize_word(part)
            if n and n in present and n not in out and len(n) > 2:
                out.append(n)
    return out[:12]


# --------------------------------------------------------------------------- prompts


def _mmss(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 60}:{t % 60:02d}"


def editorial_system(
    language: str, focus: str | None, profile_name: str, cta_hint: str | None
) -> str:
    lang = LANG_NAMES.get(language, language)
    cta_rule = (
        f"Utilise exactement cet appel à l'action : « {cta_hint} »."
        if cta_hint
        else "Propose un appel à l'action court : une question à la communauté liée au contenu "
        "réel de l'extrait, ou une invitation à s'abonner."
    )
    return f"""Tu prépares le montage d'un short vertical (TikTok, YouTube Shorts) à partir \
d'un extrait de vidéo de jeu déjà sélectionné. Profil : {profile_name}. Angle : \
{focus or "moments forts compréhensibles sans contexte"}.

Consignes impératives :
1. hook_text : accroche affichée pendant les 3 premières secondes, {MAX_HOOK_CHARS} caractères \
maximum, en {lang}. Elle ne doit JAMAIS promettre ou suggérer un événement, un résultat ou une \
émotion absents de l'extrait (pas de « vous n'allez pas croire… » si rien d'inattendu ne se \
produit). hook_kind = « quote » seulement si hook_text reprend mot pour mot une phrase \
prononcée dans la transcription fournie (dans sa langue d'origine) ; sinon « original ».
2. {cta_rule} {MAX_CTA_CHARS} caractères maximum, en {lang}.
3. keywords : 3 à 10 mots isolés de la transcription à mettre en couleur (chiffres marquants, \
noms, mots porteurs d'émotion), écrits exactement comme dans la transcription fournie.
4. zooms : 0 à {MAX_ZOOMS} zooms ponctuels, uniquement sur des moments visuellement ou \
oralement forts. t en secondes depuis le début du short, durée de 1 à 3 s. Aucun zoom vaut \
mieux qu'un zoom gratuit.
5. warnings : limites ou points de vigilance pour le montage (liste vide sinon).
6. N'invente rien : appuie-toi uniquement sur la transcription, le résumé et les moments \
fournis."""


def editorial_content(
    summary: str | None,
    reason: str | None,
    events: list[dict[str, object]],
    sentences: list[Sentence],
    duration: float,
    offset: float,
) -> list[dict[str, object]]:
    lines = "\n".join(f"[{_mmss(s.start)}–{_mmss(s.end)}] {s.text}" for s in sentences)
    from app.analysis.judge import event_time_absolute

    rel = [
        (
            event_time_absolute(float(e.get("t", 0)), offset, offset + duration) - offset,  # type: ignore[arg-type]
            e.get("description", ""),
        )
        for e in events
    ]
    moments = "\n".join(f"- {_mmss(t)} : {d}" for t, d in rel if 0 <= t <= duration)
    return [
        {
            "type": "text",
            "text": (
                f"Durée du short : {duration:.0f} s.\n"
                f"Résumé de l'extrait : {summary or 'non disponible'}\n"
                f"Pourquoi il a été retenu : {reason or 'non précisé'}\n"
                f"Moments notables (temps depuis le début du short) :\n{moments or '- aucun'}\n\n"
                f"Transcription (temps depuis le début du short) :\n{lines or '(aucune parole)'}"
            ),
        }
    ]


def translation_system(source_language: str | None, target: str) -> str:
    origin = (
        f"depuis le {LANG_NAMES.get(source_language, source_language)} " if source_language else ""
    )
    return (
        f"Tu traduis les sous-titres d'un short de jeu vidéo {origin}"
        f"vers le {LANG_NAMES.get(target, target)}. Traduis chaque phrase fidèlement, dans un "
        "registre oral naturel et concis adapté aux sous-titres. N'ajoute, ne retire et ne "
        "commente rien ; garde les noms propres, chiffres et termes de jeu tels quels si "
        "l'usage le veut. Renvoie exactement une traduction par index fourni."
    )


def translation_content(sentences: list[Sentence]) -> list[dict[str, object]]:
    body = "\n".join(f"{i}: {s.text}" for i, s in enumerate(sentences))
    return [{"type": "text", "text": f"Phrases à traduire (index: texte) :\n{body}"}]


def validate_translation(tr: Translation, count: int) -> None:
    indexes = sorted(s.index for s in tr.sentences)
    if indexes != list(range(count)):
        raise ValueError(f"traduction incomplète ({len(indexes)}/{count} phrases)")
    if any(not s.text.strip() for s in tr.sentences):
        raise ValueError("phrase traduite vide")


# --------------------------------------------------------------------------- repli sans IA


def fallback_plan(
    sentences: list[Sentence],
    peaks: list[float],
    duration: float,
    hook_enabled: bool,
    cta_text: str | None,
    language: str,
) -> EditorialPlan:
    """Plan minimal sans IA : citation réelle la plus proche du premier pic, zooms aux pics."""
    hook = ""
    if hook_enabled and sentences:
        target = peaks[0] if peaks else 0.0
        candidates = [s for s in sentences if 3 <= len(s.text) <= MAX_HOOK_CHARS] or sentences
        best = min(candidates, key=lambda s: abs(s.start - target))
        hook = best.text[:MAX_HOOK_CHARS].rstrip()
    default_cta = {"fr": "Abonne-toi pour la suite !", "en": "Follow for more!"}
    zooms = [
        ZoomMoment(t=max(0.0, p - 0.5), duration=1.5, reason="Pic d'énergie sonore")
        for p in peaks[:MAX_ZOOMS]
        if p - 0.5 >= 0 and p + 1.0 <= duration
    ]
    words = [w for s in sentences for (_, _, w) in s.words]
    numbers = [w for w in words if any(ch.isdigit() for ch in w)]
    return EditorialPlan(
        hook_text=hook,
        hook_kind="quote",
        hook_reason="Phrase réellement prononcée près du premier moment fort (sans IA).",
        cta_text=cta_text or default_cta.get(language, default_cta["en"]),
        keywords=numbers[:6],
        zooms=zooms,
        warnings=[
            "Plan éditorial construit sans IA : accroche tirée de la transcription, "
            "zooms placés sur les pics sonores."
        ],
    )
