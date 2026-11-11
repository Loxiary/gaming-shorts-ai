"""Styles de montage : valeurs par défaut, validation, conversion vers le format ASS."""

from __future__ import annotations

import re
from typing import Any

# Polices Windows épaisses, lisibles en vertical. Liste fermée : aucune valeur libre
# n'est injectée dans le fichier de sous-titres.
ALLOWED_FONTS = ("Arial Black", "Impact", "Segoe UI Black", "Bahnschrift", "Verdana")

DEFAULT_SUBTITLE_STYLE: dict[str, Any] = {
    "font": "Arial Black",
    "size": 76,
    "text_color": "#FFFFFF",
    "highlight_color": "#FFE500",  # mot en cours de prononciation
    "keyword_color": "#38E1FF",  # mots importants
    "uppercase": True,
    "max_words": 3,
}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_subtitle_style(value: dict[str, Any] | None) -> dict[str, Any]:
    style = dict(DEFAULT_SUBTITLE_STYLE)
    style.update({k: v for k, v in (value or {}).items() if k in DEFAULT_SUBTITLE_STYLE})
    if style["font"] not in ALLOWED_FONTS:
        raise ValueError(f"Police non prise en charge : {style['font']}")
    size = int(style["size"])
    if not 40 <= size <= 120:
        raise ValueError("La taille des sous-titres doit être comprise entre 40 et 120")
    style["size"] = size
    for key in ("text_color", "highlight_color", "keyword_color"):
        if not _HEX.match(str(style[key])):
            raise ValueError(f"Couleur invalide pour {key} : format #RRGGBB attendu")
        style[key] = str(style[key]).upper()
    words = int(style["max_words"])
    if not 1 <= words <= 6:
        raise ValueError("Le nombre de mots par ligne doit être compris entre 1 et 6")
    style["max_words"] = words
    style["uppercase"] = bool(style["uppercase"])
    return style


def ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR (format ASS)."""
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_inline_color(hex_color: str) -> str:
    """#RRGGBB -> &HBBGGRR& (balise \\c)."""
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H{b}{g}{r}&".upper()
