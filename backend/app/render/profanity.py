"""Censure des mots grossiers dans les textes affichés (sous-titres, accroche, appel à l'action).

Règle : on garde les deux premières lettres, les suivantes deviennent des astérisques
(« putain » → « pu**** », « fucking » → « fu***** »). La ponctuation autour du mot est
conservée. L'audio d'origine n'est PAS modifié.

Détection par liste (français et anglais), sans tenir compte des accents ni de la casse :
- ``EXACT`` : mots entiers uniquement (« con » mais pas « conseil », « ass » mais pas « class ») ;
- ``PREFIXES`` : toutes les formes qui commencent ainsi (« fuck » → fucking, fucked…).
"""

from __future__ import annotations

import re
import unicodedata

# Insultes racistes, homophobes ou discriminatoires : toujours masquées et bipées.
SLURS_EXACT = {
    "negro",
    "negros",
    "negre",
    "negres",
    "bougnoule",
    "bougnoules",
    "youpin",
    "youpins",
    "bicot",
    "bicots",
    "pede",
    "pedes",
    "tapette",
    "tapettes",
    "gouine",
    "gouines",
    "fag",
    "fags",
    "faggot",
    "faggots",
    "chink",
    "chinks",
    "spic",
    "spics",
    "kike",
    "kikes",
    "wetback",
    "wetbacks",
    "tranny",
    "retard",
    "retards",
}
SLURS_PREFIXES = ("nigg", "nigr", "niga", "negr")

EXACT = {
    # français
    "con",
    "cons",
    "conne",
    "connes",
    "cul",
    "culs",
    "merde",
    "merdes",
    "pute",
    "putes",
    "salaud",
    "salauds",
    "bite",
    "bites",
    "chier",
    "chiant",
    "chiante",
    "chiants",
    "chiantes",
    "bordel",
    "foutre",
    "nique",
    "niquer",
    "batard",
    "batards",
    "petasse",
    "petasses",
    "pd",
    "fdp",
    "ntm",
    "tg",
    "pouffiasse",
    "pouffiasses",
    # anglais
    "ass",
    "asses",
    "arse",
    "dick",
    "dicks",
    "cock",
    "cocks",
    "pussy",
    "pussies",
    "piss",
    "pissed",
    "crap",
    "crappy",
    "wtf",
    "whore",
    "whores",
    "slut",
    "sluts",
    "cunt",
    "cunts",
    "bastard",
    "bastards",
    "damn",
    "dammit",
    "goddamn",
    "goddamnit",
    "dumbass",
    "jackass",
    "smartass",
    "badass",
    "twat",
    "wanker",
    "wankers",
    "bollocks",
    "bloody",
}
PREFIXES = (
    # français
    "putain",
    "encul",
    "connard",
    "connass",
    "salop",
    "merdi",
    "emmerd",
    "niqu",
    "enfoir",
    "couill",
    "branl",
    "bordel",
    # anglais
    "fuck",
    "shit",
    "bitch",
    "motherf",
    "bullshit",
    "asshole",
    "dickhead",
    "douche",
)

_TOKEN = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)


def _fold(word: str) -> str:
    text = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def is_profane(word: str) -> bool:
    w = _fold(word)
    return (
        w in EXACT
        or w in SLURS_EXACT
        or any(w.startswith(p) for p in PREFIXES)
        or any(w.startswith(p) for p in SLURS_PREFIXES)
    )


def _mask(word: str) -> str:
    keep = min(2, max(len(word) - 1, 1))
    return word[:keep] + "*" * (len(word) - keep)


def censor_text(text: str) -> tuple[str, int]:
    """Masque les mots grossiers d'un texte libre. Retourne (texte, nombre de mots masqués).
    Les élisions sont traitées (« d'enculé » → « d'en**** »)."""
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        token = m.group(0)
        parts = re.split(r"(['’])", token)  # élision : l'ensemble, puis chaque partie
        if is_profane(token):
            count += 1
            return _mask(token)
        out = []
        for part in parts:
            if part and part not in "'’" and is_profane(part):
                count += 1
                out.append(_mask(part))
            else:
                out.append(part)
        return "".join(out)

    return _TOKEN.sub(repl, text), count


def censor_word(word: str) -> tuple[str, bool]:
    """Un mot de sous-titre (ponctuation comprise)."""
    text, n = censor_text(word)
    return text, n > 0
