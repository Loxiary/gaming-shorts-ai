from __future__ import annotations

import pytest

from app.services.source_urls import InvalidSourceUrl, parse_source_url

VALID = [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
    ("youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("  https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123  ", "dQw4w9WgXcQ"),
]


@pytest.mark.parametrize(("url", "video_id"), VALID)
def test_valid_youtube_urls(url: str, video_id: str) -> None:
    parsed = parse_source_url(url)
    assert parsed.source_type == "youtube"
    assert parsed.external_id == video_id
    assert parsed.canonical_url == f"https://www.youtube.com/watch?v={video_id}"


@pytest.mark.parametrize(
    ("url", "fragment"),
    [
        ("", "vide"),
        ("https://www.youtube.com/playlist?list=PL123", "playlists"),
        ("https://www.youtube.com/@chaine", "ne désigne pas une vidéo"),
        ("https://vimeo.com/123456", "Seuls les liens YouTube"),
        ("https://www.youtube.com.evil.example/watch?v=dQw4w9WgXcQ", "Seuls les liens YouTube"),
        ("ftp://youtube.com/watch?v=dQw4w9WgXcQ", "http(s)"),
        ("https://www.youtube.com/watch?v=trop-court", "invalide"),
        ("https://youtu.be/", "invalide"),
        ("file:///C:/video.mp4", "http(s)"),
    ],
)
def test_rejected_urls(url: str, fragment: str) -> None:
    with pytest.raises(InvalidSourceUrl) as exc:
        parse_source_url(url)
    assert fragment in str(exc.value)
