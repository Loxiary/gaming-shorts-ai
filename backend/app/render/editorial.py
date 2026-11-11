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
MAX_NARRATION_LINES = 4
MAX_NARRATION_CHARS = 160
MUSIC_MOODS = ("énergique", "calme", "épique", "drôle", "tendu", "mystérieux")
MAX_EFFECTS = 4
EFFECT_SPACING = 2.5  # secondes minimum entre deux effets (pas de surcharge)
EFFECT_DURATIONS = {"flash": (0.1, 0.5), "shake": (0.3, 1.0)}

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


class EffectMoment(BaseModel):
    t: float  # secondes depuis le début du short
    kind: Literal["flash", "shake"]
    duration: float
    reason: str


class NarrationLine(BaseModel):
    t: float  # instant souhaité, secondes depuis le début du short
    text: str


class EditorialPlan(BaseModel):
    hook_text: str
    hook_kind: Literal["quote", "original"]
    hook_reason: str
    cta_text: str
    keywords: list[str]
    zooms: list[ZoomMoment]
    warnings: list[str]
    # Phase 5 (valeurs par défaut : plans antérieurs et plan de repli sans narration).
    narration_needed: bool = False
    narration_reason: str = ""
    narration: list[NarrationLine] = []
    music_mood: str = ""
    # Phase 7 : effets ponctuels (vide pour les plans antérieurs et le plan de repli).
    effects: list[EffectMoment] = []


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
    if not plan.narration_needed and plan.narration:
        plan.narration = []
    if len(plan.narration) > MAX_NARRATION_LINES:
        raise ValueError(f"plus de {MAX_NARRATION_LINES} lignes de narration")
    for line in plan.narration:
        if not line.text.strip() or len(line.text) > MAX_NARRATION_CHARS:
            raise ValueError(f"ligne de narration vide ou de plus de {MAX_NARRATION_CHARS} car.")
        if not 0 <= line.t < duration:
            raise ValueError(f"ligne de narration hors de l'extrait (t={line.t})")
    if plan.music_mood and plan.music_mood not in MUSIC_MOODS:
        plan.music_mood = ""
    plan.effects, dropped = filter_effects(plan.effects, duration)
    plan.warnings += dropped
    return plan


def filter_effects(
    effects: list[EffectMoment], duration: float
) -> tuple[list[EffectMoment], list[str]]:
    """Garde les effets valides (dans l'extrait, durée correcte, espacés d'au moins
    EFFECT_SPACING s, MAX_EFFECTS au plus) ; écarte les autres en le signalant. Un effet
    mal placé ne doit jamais faire perdre tout le plan éditorial."""
    kept: list[EffectMoment] = []
    dropped: list[str] = []
    for e in sorted(effects, key=lambda x: x.t):
        lo, hi = EFFECT_DURATIONS[e.kind]
        why = None
        if not lo <= e.duration <= hi:
            why = f"durée {e.duration:g} s hors de {lo:g}–{hi:g} s"
        elif not (e.t >= 0.5 and e.t + e.duration <= duration - 0.5):
            why = "hors de l'extrait"
        elif kept and e.t - kept[-1].t < EFFECT_SPACING:
            why = f"moins de {EFFECT_SPACING:g} s après l'effet précédent"
        elif len(kept) >= MAX_EFFECTS:
            why = f"plus de {MAX_EFFECTS} effets"
        if why:
            dropped.append(f"Effet « {e.kind} » à {e.t:.1f} s écarté ({why}).")
        else:
            kept.append(e)
    return kept, dropped


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
    language: str,
    focus: str | None,
    profile_name: str,
    cta_hint: str | None,
    narration: bool = False,
    music: bool = False,
    effects: bool = False,
) -> str:
    lang = LANG_NAMES.get(language, language)
    effects_rule = (
        f"""
9. effects : 0 à {MAX_EFFECTS} effets ponctuels, UNIQUEMENT sur des moments réellement forts \
(explosion, impact, chute, révélation, réaction vive) et jamais par habitude : aucun effet \
vaut mieux qu'un effet gratuit. kind = « flash » (éclair blanc bref, 0,1 à 0,5 s, pour une \
révélation ou un instant marquant) ou « shake » (tremblement de caméra, 0,3 à 1 s, pour un \
impact ou une explosion). t en secondes depuis le début du short, au moins \
{EFFECT_SPACING:g} s entre deux effets. reason : le moment précis qui le justifie."""
        if effects
        else "\n9. effects : liste vide."
    )
    narration_rule = (
        f"""
7. Narration (voix de synthèse ajoutée) : narration_needed = true UNIQUEMENT si une courte \
narration apporte vraiment quelque chose (contexte indispensable absent, extrait sans parole, \
enjeu à expliquer). Sinon false, narration vide : une narration inutile dégrade le short. \
Si true : 1 à {MAX_NARRATION_LINES} lignes en {lang}, {MAX_NARRATION_CHARS} caractères maximum \
chacune, phrases simples faciles à prononcer, STRICTEMENT factuelles (seulement ce que \
montrent la transcription et les moments fournis ; aucun chiffre, nom ou événement inventé). \
t = instant souhaité en secondes depuis le début du short, placé dans un SILENCE de la \
transcription (jamais par-dessus quelqu'un qui parle). narration_reason explique le choix."""
        if narration
        else "\n7. narration_needed = false, narration vide, narration_reason vide."
    )
    music_rule = (
        "\n8. music_mood : ambiance d'une musique de fond discrète adaptée à l'extrait, parmi : "
        + ", ".join(MUSIC_MOODS)
        + ". Chaîne vide si aucune musique ne convient (dialogue dense, ambiance déjà forte)."
        if music
        else "\n8. music_mood : chaîne vide."
    )
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
fournis.{narration_rule}{music_rule}{effects_rule}"""


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
