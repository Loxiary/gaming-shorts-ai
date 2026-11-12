"""Facecam « réaction » : vidéo commune en boucle, ronde, contour jaune, en bas à gauche."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.render.ffmpeg_render import (
    REACT_MARGIN_X,
    REACT_MIN_TOP,
    REACT_RING,
    filter_graph,
    react_graph,
)
from tests.fakes import FakeEditor, make_bursty_video, requires_ffmpeg


def test_react_graph_crops_a_disk_with_a_yellow_ring() -> None:
    g = react_graph(index=2, fps=30, cx=0.43, cy=0.5, zoom=1.0, diameter=360)
    assert g.startswith("[2:v]fps=30,crop=w='ih*1.0000'")
    assert "scale=360:360" in g and "color=c=0xFFD000:s=378x378" in g
    assert "hypot(X-180,Y-180),179" in g and "hypot(X-189,Y-189),188" in g
    assert g.endswith("overlay=x=9:y=9:shortest=1[react]")
    full = filter_graph(
        layout="blur",
        src_w=1920,
        src_h=1080,
        fps=30,
        zoom="1",
        ass_file="s.ass",
        duration=70,
        react=g,
    )
    # Incrustée après le gameplay (et ses effets), avant les textes qui restent au-dessus.
    assert "[base];[2:v]" in full
    # En haut à droite, centre sur le bord supérieur du gameplay 16:9 (y = 656), sous le titre.
    assert f"[base][react]overlay=x=W-w-{REACT_MARGIN_X}:y='max({REACT_MIN_TOP},656-h/2)'" in full
    assert full.index("[base][react]overlay") < full.index("ass=s.ass")


def _react_video(settings: Settings, seconds: float = 20) -> Path:
    path = settings.data_dir / "facecam" / "react.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x20A040:s=640x360:r=30:d={seconds}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


def _pixel(video: Path, t: float, x: int, y: int) -> tuple[int, int, int]:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(t),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    img = np.frombuffer(raw, dtype=np.uint8).reshape(1920, 1080, 3)
    return tuple(int(v) for v in img[y, x])  # type: ignore[return-value]


@requires_ffmpeg
def test_render_with_looping_react_facecam(
    client: TestClient,
    migrated: Settings,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    from tests.test_render_pipeline import SECONDS, _candidate, _profile_update, _render, _worker

    migrated.render_x264_preset = "ultrafast"
    migrated.frames_per_candidate = 2
    video = make_bursty_video(tmp_path / "v.mp4", SECONDS, bursts=(30, 70))
    worker = _worker(migrated, session_factory, video, FakeEditor())
    _, cand = _candidate(client, worker)

    # Sans fichier : le short est monté sans facecam, et c'est signalé.
    missing = _render(client, worker, cand["id"])
    assert missing["job_status"] == "completed", missing["job_error"]
    assert any("Facecam réaction absente" in w for w in missing["plan"]["warnings"])

    migrated.react_video = "facecam/react.mp4"
    _react_video(migrated, seconds=20)  # plus courte que le short : doit boucler
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    assert render["qc_passed"] is True
    short = migrated.resolve_data_path(
        f"projects/{render['project_id']}/renders/{render['id']}/short.mp4"
    )
    ring = REACT_RING // 2
    diameter = migrated.react_diameter + 2 * REACT_RING
    # Vidéo de test 4:3 (320×240) : gameplay de 810 px, haut à 555 → cercle plaqué sous le titre.
    top = max(REACT_MIN_TOP, (1920 - 810) // 2 - diameter // 2)
    cy = top + diameter // 2
    right = 1080 - REACT_MARGIN_X
    for t in (5.0, render["duration_seconds"] - 3):  # avant et après la fin de la vidéo (boucle)
        r, g, b = _pixel(short, t, right - diameter + ring, cy)  # bord gauche : contour jaune
        assert r > 200 and g > 170 and b < 90, (t, r, g, b)
        r, g, b = _pixel(short, t, right - diameter // 2, cy)  # centre : la vidéo
        assert g > r and g > b, (t, r, g, b)
    assert not any("Facecam réaction" in w for w in render["plan"]["warnings"])

    _profile_update(client, react_overlay=False)
    off = _render(client, worker, cand["id"])
    assert not any("Facecam réaction" in w for w in off["plan"]["warnings"])
