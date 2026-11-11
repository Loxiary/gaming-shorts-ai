"""Détection d'un facecam (webcam du joueur incrustée) et recadrage pour l'exclure.

Principe : un facecam est un visage PERSISTANT, au MÊME endroit, près d'un bord de l'image,
sur la majorité des images échantillonnées. Un visage de personnage du jeu bouge ou disparaît.
Aucune reconnaissance d'identité : seule la position d'un visage est utilisée.

La logique de décision (``analyze_detections``) est pure et testée sans modèle ; la détection
elle-même (YuNet, OpenCV) est fournie par ``app.audio.toolkit``.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

MIN_SCORE = 0.7
CLUSTER_RADIUS = 0.07  # distance normalisée entre centres d'un même facecam
DETECTED_PRESENCE = 0.5  # visage au même endroit sur au moins la moitié des images
UNCERTAIN_PRESENCE = 0.25
CAM_EXPAND = 2.6  # le cadre de la webcam est ~2,6 fois plus grand que le visage
EDGE_SNAP = 0.08
MAX_LOSS_WARNING = 0.35


@dataclass(frozen=True)
class Face:
    """Boîte normalisée (0..1) d'un visage détecté et son score de confiance."""

    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def _clamp(v: float) -> float:
    return min(max(v, 0.0), 1.0)


def _crop_options(cam: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Recadrages qui excluent entièrement le cadre ``cam`` (x0, y0, x1, y1), avec la part
    d'image perdue pour chacun."""
    x0, y0, x1, y1 = cam
    opts: list[dict[str, Any]] = []
    if x0 > 0.05:  # garder la partie gauche
        opts.append({"side": "droite", "crop": (0.0, 0.0, x0, 1.0), "loss": 1 - x0})
    if x1 < 0.95:  # garder la partie droite
        opts.append({"side": "gauche", "crop": (x1, 0.0, 1 - x1, 1.0), "loss": x1})
    if y0 > 0.05:  # garder le haut
        opts.append({"side": "bas", "crop": (0.0, 0.0, 1.0, y0), "loss": 1 - y0})
    if y1 < 0.95:  # garder le bas
        opts.append({"side": "haut", "crop": (0.0, y1, 1.0, 1 - y1), "loss": y1})
    return sorted(opts, key=lambda o: o["loss"])


def analyze_detections(frames: list[list[Face]]) -> dict[str, Any]:
    """Décide si un facecam est présent et propose un recadrage (coordonnées normalisées)."""
    n = len(frames)
    base: dict[str, Any] = {"frames_analyzed": n, "presence": 0.0, "crop": None, "warning": None}
    if n == 0:
        return {**base, "status": "unavailable", "warning": "Aucune image analysable."}
    faces = [[f for f in fr if f.score >= MIN_SCORE and 0.02 <= f.w <= 0.45] for fr in frames]
    best: list[Face] = []
    for fr in faces:
        for f in fr:
            cluster = []
            for other in faces:
                near = [
                    g
                    for g in other
                    if abs(g.cx - f.cx) <= CLUSTER_RADIUS and abs(g.cy - f.cy) <= CLUSTER_RADIUS
                ]
                if near:
                    cluster.append(max(near, key=lambda g: g.score))
            if len(cluster) > len(best):
                best = cluster
    presence = len(best) / n
    base["presence"] = round(presence, 2)
    if presence < UNCERTAIN_PRESENCE:
        return {**base, "status": "none"}

    fx, fy = median(f.x for f in best), median(f.y for f in best)
    fw, fh = median(f.w for f in best), median(f.h for f in best)
    cx, cy = fx + fw / 2, fy + fh / 2
    base["face_box"] = [round(v, 4) for v in (fx, fy, fw, fh)]
    central = abs(cx - 0.5) < 0.2 and abs(cy - 0.5) < 0.2
    if presence < DETECTED_PRESENCE or central:
        why = (
            "visage persistant au centre de l'image (personnage du jeu ?)"
            if central
            else f"visage au même endroit sur {presence:.0%} des images seulement"
        )
        return {
            **base,
            "status": "uncertain",
            "warning": f"Facecam incertain : {why}. Aucun recadrage appliqué ; vérifiez le short.",
        }

    cw, ch = min(fw * CAM_EXPAND, 0.6), min(fh * CAM_EXPAND, 0.6)
    x0, y0 = _clamp(cx - cw / 2), _clamp(cy - ch / 2)
    x1, y1 = _clamp(cx + cw / 2), _clamp(cy + ch / 2)
    # Un facecam est presque toujours collé à un bord : on l'y prolonge.
    x0 = 0.0 if x0 < EDGE_SNAP else x0
    y0 = 0.0 if y0 < EDGE_SNAP else y0
    x1 = 1.0 if x1 > 1 - EDGE_SNAP else x1
    y1 = 1.0 if y1 > 1 - EDGE_SNAP else y1
    cam = (x0, y0, x1, y1)
    base["cam_box"] = [round(v, 4) for v in (x0, y0, x1 - x0, y1 - y0)]
    options = _crop_options(cam)
    if not options:
        return {
            **base,
            "status": "detected",
            "warning": "Facecam détecté mais trop grand pour être exclu par recadrage.",
        }
    best_opt = options[0]
    result = {
        **base,
        "status": "detected",
        "crop": [round(v, 4) for v in best_opt["crop"]],
        "crop_side": best_opt["side"],
        "loss": round(best_opt["loss"], 3),
    }
    if best_opt["loss"] > MAX_LOSS_WARNING:
        result["warning"] = (
            f"Le recadrage qui exclut le facecam retire {best_opt['loss']:.0%} de l'image : "
            "vérifiez que l'action reste lisible."
        )
    return result
