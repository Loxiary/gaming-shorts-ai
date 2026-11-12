"""Validation hors ligne des liens importés (aucune requête réseau ici).

Seuls les liens vers UNE vidéo YouTube sont acceptés. Les playlists, chaînes et autres sites
sont refusés avec un message explicite. Les vérifications en ligne (vidéo privée, direct,
restriction d'âge, DRM) ont lieu dans l'étape « validating_source » du worker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_PATH_PREFIXES = ("/shorts/", "/live/", "/embed/")


class InvalidSourceUrl(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSource:
    source_type: str
    external_id: str
    canonical_url: str


def parse_source_url(raw: str) -> ParsedSource:
    url = raw.strip()
    if not url:
        raise InvalidSourceUrl("Lien vide.")
    if len(url) > 500:
        raise InvalidSourceUrl("Lien trop long.")
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise InvalidSourceUrl("Seuls les liens http(s) sont acceptés.")
    host = (parts.hostname or "").lower()

    video_id: str | None = None
    if host in _SHORT_HOSTS:
        video_id = parts.path.strip("/").split("/")[0]
    elif host in _YOUTUBE_HOSTS:
        query = parse_qs(parts.query)
        if parts.path == "/watch":
            video_id = (query.get("v") or [None])[0]
        elif parts.path.startswith(_PATH_PREFIXES):
            video_id = parts.path.split("/")[2] if len(parts.path.split("/")) > 2 else None
        elif parts.path == "/playlist" or "list" in query:
            raise InvalidSourceUrl(
                "Les playlists ne sont pas prises en charge : importez chaque vidéo séparément."
            )
        else:
            raise InvalidSourceUrl("Ce lien YouTube ne désigne pas une vidéo (chaîne, recherche…).")
    else:
        raise InvalidSourceUrl(
            "Seuls les liens YouTube (youtube.com, youtu.be) sont pris en charge pour le moment."
        )

    if not video_id or not _VIDEO_ID.match(video_id):
        raise InvalidSourceUrl("Identifiant de vidéo YouTube introuvable ou invalide dans le lien.")
    return ParsedSource(
        source_type="youtube",
        external_id=video_id,
        canonical_url=f"https://www.youtube.com/watch?v={video_id}",
    )
