"""Cadrage « gros plan » : un carré découpé dans le gameplay qui suit le visage à l'écran.

Le visage le plus grand de chaque image échantillonnée (détecteur YuNet, position seulement,
aucune reconnaissance d'identité) donne le centre horizontal du cadre. La trajectoire est
lissée (médiane, vitesse de panoramique limitée) pour éviter tout tremblement, puis traduite
en expression FFmpeg linéaire par morceaux. Sans visage : on garde la dernière position,
au départ le centre de l'image.
"""

from __future__ import annotations

from statistics import median

from app.render.facecam import Face

MIN_SCORE = 0.6
MIN_FACE_W = 0.03  # visage trop petit (figurant au loin) ignoré
MAX_PAN_PER_S = 0.08  # vitesse de panoramique maximale (fraction de largeur par seconde)
SAMPLE_EVERY = 1.5  # secondes entre deux images analysées


def _pick(faces: list[Face], exclude: list[float] | None) -> float | None:
    """Centre x du plus grand visage, hors zone du facecam éventuel (x, y, w, h)."""
    best: Face | None = None
    for f in faces:
        if f.score < MIN_SCORE or f.w < MIN_FACE_W:
            continue
        if exclude:
            ex, ey, ew, eh = exclude
            if ex <= f.cx <= ex + ew and ey <= f.cy <= ey + eh:
                continue
        if best is None or f.w * f.h > best.w * best.h:
            best = f
    return best.cx if best else None


def focus_track(
    samples: list[tuple[float, list[Face]]], exclude: list[float] | None = None
) -> list[tuple[float, float]]:
    """(t relatif au short, centre x normalisé) lissé ; liste vide si aucun visage du tout."""
    raw: list[tuple[float, float | None]] = [(t, _pick(f, exclude)) for t, f in samples]
    if not any(x is not None for _, x in raw):
        return []
    first = next(x for _, x in raw if x is not None)
    filled: list[tuple[float, float]] = []
    last = first
    for t, x in raw:
        last = x if x is not None else last
        filled.append((t, last))
    # Médiane sur 3 points : supprime les sauts isolés (faux visage, coupe d'une image).
    smooth = [
        (t, median(x for _, x in filled[max(0, i - 1) : i + 2])) for i, (t, _) in enumerate(filled)
    ]
    out: list[tuple[float, float]] = []
    for t, x in smooth:
        if out:
            pt, px = out[-1]
            step = MAX_PAN_PER_S * max(t - pt, 0.0)
            x = min(max(x, px - step), px + step)
        out.append((round(t, 2), round(x, 4)))
    return out


def center_expression(track: list[tuple[float, float]]) -> str:
    """Centre x(t) normalisé, linéaire par morceaux (constant avant/après les extrémités)."""
    if not track:
        return "0.5"
    if len(track) == 1:
        return f"{track[0][1]:.4f}"
    terms = [f"{track[0][1]:.4f}*lt(t,{track[0][0]:.2f})"]
    for (t0, x0), (t1, x1) in zip(track, track[1:], strict=False):
        if t1 <= t0:
            continue
        slope = (x1 - x0) / (t1 - t0)
        terms.append(f"between(t,{t0:.2f},{t1:.2f}-0.001)*({x0:.4f}+{slope:.5f}*(t-{t0:.2f}))")
    terms.append(f"{track[-1][1]:.4f}*gte(t,{track[-1][0]:.2f}-0.001)")
    return "+".join(terms)
