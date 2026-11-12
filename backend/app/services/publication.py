"""Textes de publication d'un short (TikTok, YouTube Shorts) et musique conseillée à l'upload.

L'IA rédige le contexte, la question, l'accroche TikTok, le titre YouTube et les hashtags ;
le code ajoute les crédits obligatoires (source, voix sous licence CC BY, musique) pour qu'ils
ne soient jamais oubliés ni inventés, puis masque les mots grossiers éventuels.

Musique : les morceaux des bibliothèques sonores de TikTok et de YouTube sont sous licence
pour un usage sur la plateforme, À CONDITION d'être ajoutés dans l'éditeur de la plateforme
au moment de l'upload. Ils ne sont donc jamais incrustés dans le fichier : on indique seulement
quoi chercher.
"""

from __future__ import annotations

import re
from typing import Any

from app.render import editorial as ed
from app.render.profanity import censor_text

PLATFORM_MUSIC_NOTE = (
    "À ajouter vous-même pendant l'upload, depuis la bibliothèque sonore de TikTok ou de "
    "YouTube Shorts (morceaux sous licence pour la plateforme). Un compte professionnel TikTok "
    "est limité à la « Commercial Music Library ». N'incrustez pas de musique du commerce dans "
    "le fichier."
)


def _game_tag(game: str | None) -> list[str]:
    if not game:
        return []
    tag = re.sub(r"[^\w]", "", game, flags=re.UNICODE)
    return [f"#{tag.lower()}"] if tag else []


def _source_credit(source: dict[str, Any]) -> str | None:
    if source.get("rights_status") == "owned":
        return None
    who = source.get("uploader") or "créateur inconnu"
    title = source.get("title") or "vidéo d'origine"
    url = source.get("url") or ""
    return f"Source : « {title} » — {who}" + (f" ({url})" if url else "")


def build_publication(
    *,
    plan: ed.EditorialPlan,
    source: dict[str, Any],
    credits: list[dict[str, str]],
    candidate_summary: str | None,
    game: str | None,
    censor: bool = True,
    series: dict[str, Any] | None = None,
    language: str = "fr",
) -> dict[str, Any]:
    pub = plan.publication
    if pub is None:  # plan sans IA : textes minimaux, signalés comme tels
        pub = ed.Publication(
            context=candidate_summary or "",
            question=plan.cta_text or "",
            tiktok_caption=plan.hook_text or "",
            youtube_title=plan.hook_text or (source.get("title") or "Short gaming"),
            hashtags=["#gaming", *_game_tag(game), "#shorts"],
        )
        generated = False
    else:
        generated = True
    pub = ed.clean_publication(pub)
    hashtags = pub.hashtags or ["#gaming", *_game_tag(game)]
    credit_lines = [c for c in [_source_credit(source)] if c] + [c["text"] for c in credits]
    tags = " ".join(hashtags)

    tiktok = " ".join(x for x in (pub.tiktok_caption, pub.question) if x)
    tiktok_full = "\n\n".join(x for x in (tiktok, tags, "\n".join(credit_lines)) if x)
    yt_desc = "\n\n".join(
        x for x in (pub.context, pub.question, "\n".join(credit_lines), tags) if x
    )
    title = pub.youtube_title
    if series and series.get("total", 1) > 1:
        word = "Partie" if language == "fr" else "Part"
        tag = f"({word} {series['index']}/{series['total']})"
        title = f"{title} {tag}"
        tiktok_full = f"{tag} {tiktok_full}"
    texts = {"tiktok": tiktok_full, "title": title, "description": yt_desc}
    censored = 0
    if censor:
        for k, v in texts.items():
            texts[k], n = censor_text(v)
            censored += n

    music = plan.music_suggestion
    return {
        "generated_by_ai": generated,
        "tiktok": {"caption": texts["tiktok"]},
        "youtube": {"title": texts["title"], "description": texts["description"]},
        "context": pub.context,
        "question": pub.question,
        "hashtags": hashtags,
        "credits": credit_lines,
        "music_suggestion": (
            {**music.model_dump(), "note": PLATFORM_MUSIC_NOTE} if music is not None else None
        ),
        "censored_words": censored,
    }
