"""Construction des sous-titres (groupes de mots synchronisés) et du fichier ASS.

- Langue d'origine : un groupe de 1 à N mots s'affiche à la fois, le mot en cours de
  prononciation est surligné (timings mot à mot de la transcription).
- Traduction : chaque phrase traduite est découpée en groupes répartis sur la durée de la
  phrase d'origine (pas de surlignage mot à mot, les timings n'existent pas en traduction).
- Accroche (3 premières s) et appel à l'action (4 dernières s) en haut de l'écran, pour ne
  jamais masquer le gameplay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.render.editorial import Sentence, normalize_word
from app.render.style import ass_color, ass_inline_color

PLAY_W, PLAY_H = 1080, 1920
HOOK_SECONDS = 3.0
CTA_SECONDS = 4.0
MAX_GAP = 0.6  # silence au-delà duquel un groupe se termine
MAX_CHARS = 24
POP = "{\\fscx118\\fscy118\\t(0,140,\\fscx100\\fscy100)}"  # apparition d'un groupe


@dataclass
class Cue:
    start: float
    end: float
    words: list[tuple[float, float, str]] = field(default_factory=list)
    karaoke: bool = True

    @property
    def text(self) -> str:
        return " ".join(w for _, _, w in self.words)

    def to_json(self) -> dict[str, Any]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "words": [[round(a, 3), round(b, 3), w] for a, b, w in self.words],
            "karaoke": self.karaoke,
        }


def _closes_sentence(word: str) -> bool:
    return word.rstrip().endswith((".", "!", "?", "…"))


def cues_from_words(
    words: list[tuple[float, float, str]], max_words: int, duration: float
) -> list[Cue]:
    cues: list[Cue] = []
    current: list[tuple[float, float, str]] = []
    for w in words:
        text = w[2].strip()
        if not text:
            continue
        w = (w[0], w[1], text)
        if current and (
            len(current) >= max_words
            or w[0] - current[-1][1] > MAX_GAP
            or len(" ".join(x[2] for x in current + [w])) > MAX_CHARS
        ):
            cues.append(Cue(current[0][0], current[-1][1], current))
            current = []
        current.append(w)
        if _closes_sentence(text):
            cues.append(Cue(current[0][0], current[-1][1], current))
            current = []
    if current:
        cues.append(Cue(current[0][0], current[-1][1], current))
    # Chaque groupe reste affiché jusqu'au suivant (au plus 0,4 s après le dernier mot).
    for i, cue in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else duration
        cue.end = max(cue.start + 0.2, min(nxt, cue.words[-1][1] + 0.4, duration))
        cue.start = max(0.0, cue.start)
    return [c for c in cues if c.end > c.start]


def cues_from_translation(
    sentences: list[Sentence], translated: list[str], max_words: int, duration: float
) -> list[Cue]:
    cues: list[Cue] = []
    for sentence, text in zip(sentences, translated, strict=True):
        tokens = text.split()
        if not tokens:
            continue
        groups: list[list[str]] = []
        for tok in tokens:
            if (
                groups
                and len(groups[-1]) < max_words
                and len(" ".join(groups[-1] + [tok])) <= MAX_CHARS
            ):
                groups[-1].append(tok)
            else:
                groups.append([tok])
        # Pas de minutage mot à mot en traduction : chaque mot reçoit une part de la durée de
        # la phrase d'origine proportionnelle à sa longueur (surlignage animé quand même).
        span = max(sentence.end - sentence.start, 0.3)
        total = sum(len(w) + 1 for g in groups for w in g) or 1
        t = sentence.start
        for g in groups:
            words = []
            for w in g:
                d = span * (len(w) + 1) / total
                words.append((t, min(t + d, duration), w))
                t += d
            cues.append(Cue(words[0][0], min(words[-1][1], duration), words, karaoke=True))
    return [c for c in cues if c.end > c.start and c.start < duration]


# --------------------------------------------------------------------------- ASS


def _escape(text: str) -> str:
    # Aucun texte (transcription, IA) ne doit pouvoir injecter de balise ASS.
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


MID_CTA_SECONDS = 3.5
REACTION_SECONDS = 1.3
POP_BIG = "{\\fad(150,0)\\fscx70\\fscy70\\t(0,200,\\fscx100\\fscy100)}"
REACTION_LABELS = {
    "fr": {
        "laugh": "MDR 😂",
        "shock": "QUOI ?! 😳",
        "fail": "OH NON 💀",
        "hype": "ÉPIQUE 🔥",
        "cringe": "GÊNANT 😬",
    },
    "en": {
        "laugh": "LOL 😂",
        "shock": "WHAT?! 😳",
        "fail": "OH NO 💀",
        "hype": "EPIC 🔥",
        "cringe": "CRINGE 😬",
    },
}
TITLE_MAX_SIZE = 112
TITLE_MIN_SIZE = 70
TITLE_HIGHLIGHT = "#FFD000"


def balance_title(text: str, keep: str = "") -> list[str]:
    """Coupe le titre en deux lignes de longueurs proches (une seule ligne s'il est court),
    sans jamais couper à l'intérieur du groupe de mots ``keep`` (le mot fort coloré)."""
    words = text.split()
    if len(text) <= 18 or len(words) < 2:
        return [text]
    lo = text.lower().find(keep.lower()) if keep else -1
    hi = lo + len(keep)

    def allowed(i: int) -> bool:
        cut = len(" ".join(words[:i]))  # position de l'espace de coupure
        return lo < 0 or not lo < cut < hi

    splits = [i for i in range(1, len(words)) if allowed(i)] or list(range(1, len(words)))
    best = min(splits, key=lambda i: max(len(" ".join(words[:i])), len(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def title_size(lines: list[str]) -> int:
    """Le plus gros possible : ~0,45 em par caractère (mesuré sur un rendu réel, police grasse)
    dans 940 px de large."""
    longest = max(max((len(x) for x in lines), default=1), 1)
    return int(min(TITLE_MAX_SIZE, max(TITLE_MIN_SIZE, 940 / (0.45 * longest))))


def title_ass(text: str, highlight: str = "") -> str:
    """Texte ASS du titre : deux lignes équilibrées, mot fort en couleur, entrée animée."""
    color = ass_inline_color(TITLE_HIGHLIGHT)
    white = ass_inline_color("#FFFFFF")
    out = []
    for line in balance_title(text, highlight):
        i = line.lower().find(highlight.lower()) if highlight else -1
        if i >= 0:
            j = i + len(highlight)
            out.append(
                f"{_escape(line[:i])}{{\\c{color}}}{_escape(line[i:j])}"
                f"{{\\c{white}}}{_escape(line[j:])}"
            )
        else:
            out.append(_escape(line))
    pop = "{\\fad(120,0)\\fscx55\\fscy55\\t(0,260,\\fscx100\\fscy100)}"
    return pop + "\\N".join(out)


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _hook_size(text: str, base: int) -> int:
    """Titre : le plus gros possible en restant sur deux lignes de 1080 px."""
    n = len(text)
    return base if n <= 18 else int(base * 0.9) if n <= 34 else int(base * 0.78)


def build_ass(
    *,
    cues: list[Cue],
    style: dict[str, Any],
    keywords: list[str],
    hook: str | None,
    cta: str | None,
    duration: float,
    layout: str,
    title_highlight: str = "",
    series: dict[str, int] | None = None,
    mid_cta: tuple[float, str] | None = None,
    reactions: list[tuple[float, str]] | None = None,
    reaction_anchor: tuple[int, int] = (680, 780),
) -> str:
    font = style["font"]
    size = style["size"]
    text_c = ass_color(style["text_color"])
    upper = style["uppercase"]
    hi = ass_inline_color(style["highlight_color"])
    kw = ass_inline_color(style["keyword_color"])
    base = ass_inline_color(style["text_color"])
    keyset = {normalize_word(k) for k in keywords}
    sub_margin = 520 if layout == "blur" else 380  # gros plan : sur le bas du gameplay
    cta_margin = 200 if layout == "blur" else 140  # en bas, sous les sous-titres
    accent_box = ass_color("#7C5CFF")  # fond de l'accroche
    cta_box = ass_color("#000000", alpha=0x30)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_W}
PlayResY: {PLAY_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},{size},{text_c},{text_c},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,70,70,{sub_margin},1
Style: Hook,{font},{title_size(balance_title(hook or "", title_highlight))},&H00FFFFFF,&H00FFFFFF,{accent_box},{accent_box},-1,0,0,0,100,100,0,0,3,18,0,8,60,60,150,1
Style: Badge,{font},44,&H00101010,&H00101010,{ass_color(TITLE_HIGHLIGHT)},{ass_color(TITLE_HIGHLIGHT)},-1,0,0,0,100,100,0,0,3,10,0,7,40,40,40,1
Style: React,{font},84,&H0000D0FF,&H0000D0FF,&H00101010,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,5,10,10,10,1
Style: Cta,{font},70,&H00FFFFFF,&H00FFFFFF,{cta_box},{cta_box},-1,0,0,0,100,100,0,0,3,14,0,2,90,90,{cta_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: list[str] = []

    def word_text(w: str) -> str:
        return _escape(w.upper() if upper else w)

    for cue in cues:
        if cue.karaoke:
            for i, (ws, _we, _w) in enumerate(cue.words):
                start = cue.start if i == 0 else ws
                end = cue.words[i + 1][0] if i + 1 < len(cue.words) else cue.end
                if end <= start:
                    continue
                parts = []
                for j, (_, _, w) in enumerate(cue.words):
                    color = hi if j == i else kw if normalize_word(w) in keyset else base
                    parts.append(f"{{\\c{color}}}{word_text(w)}")
                pop = POP if i == 0 else ""
                lines.append(
                    f"Dialogue: 0,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{pop}{' '.join(parts)}"
                )
        else:
            parts = [
                f"{{\\c{kw if normalize_word(w) in keyset else base}}}{word_text(w)}"
                for _, _, w in cue.words
            ]
            lines.append(
                f"Dialogue: 0,{_ts(cue.start)},{_ts(cue.end)},Sub,,0,0,0,,{POP}{' '.join(parts)}"
            )

    if hook:
        # Titre affiché pendant TOUTE la vidéo (et lu par la voix au début).
        lines.append(
            f"Dialogue: 2,{_ts(0)},{_ts(duration)},Hook,,0,0,0,,{title_ass(hook, title_highlight)}"
        )
    if series and series.get("total", 1) > 1:
        label = series.get("label") or "PARTIE"
        lines.append(
            f"Dialogue: 3,{_ts(0)},{_ts(duration)},Badge,,0,0,0,,"
            f"{_escape(str(label))} {series['index']}/{series['total']}"
        )
    if mid_cta and mid_cta[1].strip():
        t0, text = mid_cta
        lines.append(
            f"Dialogue: 2,{_ts(t0)},{_ts(min(t0 + MID_CTA_SECONDS, duration))},Cta,,0,0,0,,"
            f"{POP_BIG}{_escape(text)}"
        )
    x, y = reaction_anchor
    for i, (t0, label) in enumerate(reactions or []):
        tilt = -12 if i % 2 == 0 else 10  # légère alternance : effet « autocollant »
        lines.append(
            f"Dialogue: 4,{_ts(t0)},{_ts(min(t0 + REACTION_SECONDS, duration))},React,,0,0,0,,"
            f"{{\\an5\\pos({x},{y})\\frz{tilt}\\fscx0\\fscy0"
            f"\\t(0,120,\\fscx125\\fscy125)\\t(120,220,\\fscx100\\fscy100)"
            f"\\fad(0,200)}}{_escape(label)}"
        )
    if cta:
        start = max(duration - CTA_SECONDS, 0.0)
        lines.append(
            f"Dialogue: 2,{_ts(start)},{_ts(duration)},Cta,,0,0,0,,{POP_BIG}{_escape(cta)}"
        )
    return header + "\n".join(lines) + "\n"
