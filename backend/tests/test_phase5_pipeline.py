"""Phase 5 de bout en bout : bibliothèque musicale, facecam, musique d'origine, narration,
mixage, aperçu audio, risques et fiche d'export. FFmpeg réel ; modèles (PANNs, Demucs, Piper,
YuNet) simulés par une boîte à outils factice — aucun téléchargement, aucun appel payant.
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.media.ffmpeg import FfmpegTool
from app.adapters.registry import Adapters
from app.audio.panns import AudioTags
from app.audio.tts import SpokenLine
from app.core.config import Settings
from app.render.facecam import Face
from app.workers.runner import Worker
from tests.fakes import FakeEditor, FakeJudge, SpeechTranscriber, requires_ffmpeg
from tests.test_render_pipeline import SECONDS, _candidate, _Copy, _profile_update, _render

pytestmark = requires_ffmpeg


class _Detector:
    """1er passage : musique partout ; après atténuation : plus de musique."""

    def __init__(self) -> None:
        self.calls = 0

    def tag(self, audio: np.ndarray) -> AudioTags:
        self.calls += 1
        n = max(1, int(np.ceil(len(audio) / 16_000)))
        level = 0.9 if self.calls == 1 else 0.05
        return AudioTags(music=[level] * n, speech=[0.2] * n, singing=[0.0] * n)


class _Separator:
    """Tout le signal est rangé dans « other » : l'atténuation doit le réduire."""

    def separate(self, stereo: np.ndarray) -> dict[str, np.ndarray]:
        zero = np.zeros_like(stereo)
        return {"vocals": zero, "drums": zero, "bass": zero, "other": stereo.copy()}


class _TTS:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def available(self, voice: str) -> bool:
        return True

    def synthesize(self, text: str, voice: str, out: Path, speed: float = 1.0) -> SpokenLine:
        self.texts.append(text)
        out.parent.mkdir(parents=True, exist_ok=True)
        sr = 22_050
        t = np.arange(int(1.5 * sr)) / sr
        pcm = (np.sin(2 * np.pi * 220 * t) * 0.3 * 32767).astype(np.int16)
        with wave.open(str(out), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())
        return SpokenLine(out, 1.5, sr)


class FakeToolkit:
    def __init__(self, face: Face | None = None) -> None:
        self.detector = _Detector()
        self.tts_engine = _TTS()
        self.face = face
        self.face_calls = 0

    def has(self, asset_id: str) -> bool:
        return True

    def voices(self) -> list[str]:
        return ["fr_FR-siwis-medium", "en_US-joe-medium"]

    def music_detector(self) -> _Detector:
        return self.detector

    def separator(self) -> _Separator:
        return _Separator()

    def tts(self) -> _TTS:
        return self.tts_engine

    def detect_faces(self, image: np.ndarray) -> list[Face]:
        self.face_calls += 1
        return [self.face] if self.face else []


def _worker(settings: Settings, sf, video: Path, editor, toolkit) -> Worker:  # type: ignore[no-untyped-def]
    return Worker(
        settings,
        sf,
        Adapters(
            downloader=_Copy(video),
            media=FfmpegTool(),
            transcriber=SpeechTranscriber(SECONDS),
            judge=FakeJudge(score=8),
            editor=editor,
            audio=toolkit,
        ),
    )


@pytest.fixture(scope="module")
def video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from tests.fakes import make_bursty_video

    return make_bursty_video(tmp_path_factory.mktemp("media5") / "v.mp4", SECONDS, bursts=(30, 70))


@pytest.fixture
def fast_settings(migrated: Settings) -> Settings:
    migrated.render_x264_preset = "ultrafast"
    migrated.frames_per_candidate = 2
    return migrated


def _music_file(settings: Settings, name: str = "Ambiance calme.wav") -> Path:
    path = settings.subdir("music") / name
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
            "sine=frequency=523:sample_rate=44100:duration=20",
            "-ac",
            "2",
            str(path),
        ],
        check=True,
    )
    return path


def test_music_library_scan_license_and_status(client: TestClient, migrated: Settings) -> None:
    _music_file(migrated)
    (migrated.subdir("music") / "notes.txt").write_text("pas de l'audio", encoding="utf-8")
    scan = client.post("/api/music/scan").json()
    assert scan["added"] == 1 and scan["total"] == 1 and scan["errors"] == []
    assert client.post("/api/music/scan").json()["added"] == 0  # idempotent
    track = client.get("/api/music").json()[0]
    assert track["usable"] is False and track["duration_seconds"] == pytest.approx(20, abs=0.2)

    # Confirmer l'autorisation exige une licence ; ambiance limitée à la liste connue.
    body = {"title": "Calme", "license_confirmed": True}
    assert client.patch(f"/api/music/{track['id']}", json=body).status_code == 400
    bad = client.patch(f"/api/music/{track['id']}", json={"moods": ["disco"]})
    assert bad.status_code == 422
    ok = client.patch(
        f"/api/music/{track['id']}",
        json={
            "title": "Calme",
            "artist": "Test",
            "license": "CC BY 4.0",
            "source_url": "https://example.org/calme",
            "moods": ["calme", "Épique"],
            "license_confirmed": True,
        },
    ).json()
    assert ok["usable"] is True and ok["moods"] == ["calme", "épique"]
    assert client.get(ok["audio_url"]).status_code == 200

    # Fichier supprimé du dossier : sa fiche disparaît à la prochaine analyse.
    (migrated.subdir("music") / "Ambiance calme.wav").unlink()
    assert client.post("/api/music/scan").json()["removed"] == 1
    assert client.get("/api/music").json() == []

    status = client.get("/api/audio/status").json()
    assert {a["id"] for a in status["assets"]} >= {"fr_FR-siwis-medium", "htdemucs", "yunet"}
    assert "calme" in status["moods"]


def test_profile_accepts_audio_settings_and_rejects_unknown_voice(client: TestClient) -> None:
    _profile_update(
        client,
        narration_voice="en_US-joe-medium",
        music_level_db=-22,
        source_music_mode="detect",
        facecam_mode="off",
    )
    p = next(p for p in client.get("/api/profiles").json() if p["is_default"])
    assert p["narration_voice"] == "en_US-joe-medium" and p["music_level_db"] == -22
    assert p["source_music_mode"] == "detect" and p["facecam_mode"] == "off"
    body = {k: v for k, v in p.items() if k not in {"id", "created_at", "updated_at"}}
    r = client.put(f"/api/profiles/{p['id']}", json=body | {"narration_voice": "inconnue"})
    assert r.status_code == 422


def test_full_phase5_render(
    client: TestClient, fast_settings: Settings, session_factory: sessionmaker[Session], video: Path
) -> None:
    _music_file(fast_settings)
    client.post("/api/music/scan")
    track = client.get("/api/music").json()[0]
    client.patch(
        f"/api/music/{track['id']}",
        json={
            "title": "Calme",
            "artist": "Test",
            "license": "CC BY 4.0",
            "moods": ["calme"],
            "license_confirmed": True,
        },
    )
    # Phrases toutes les 8 s (mots de t à t+4,8 s) : silences de ~3 s pour la narration.
    editor = FakeEditor(
        narration=[(2.0, "Il lance la partie."), (13.5, "La base grandit.")], music_mood="calme"
    )
    toolkit = FakeToolkit(face=Face(0.82, 0.70, 0.08, 0.14, 0.95))
    worker = _worker(fast_settings, session_factory, video, editor, toolkit)
    pid, cand = _candidate(client, worker)
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    assert "STRICTEMENT factuelles" in editor.systems[-1]

    # Facecam : détecté sur toutes les images, exclu par recadrage du côté droit.
    fc = render["facecam"]
    assert toolkit.face_calls == 10
    assert fc["status"] == "detected" and fc["crop_side"] == "droite" and fc["presence"] == 1.0
    probe = FfmpegTool().probe(
        fast_settings.resolve_data_path(f"projects/{pid}/renders/{render['id']}/short.mp4")
    )
    assert (probe.width, probe.height) == (1080, 1920) and probe.audio_codec == "aac"

    # Audio : musique détectée puis atténuée, narration placée dans les silences, musique.
    audio = render["audio_report"]
    sm = audio["source_music"]
    assert sm["status"] == "detected" and sm["attenuated"] and sm["residual_ratio"] == 0
    narr = audio["narration"]
    assert narr["status"] == "added" and narr["voice"] == "fr_FR-siwis-medium"
    assert [line["text"] for line in narr["lines"]] == ["Il lance la partie.", "La base grandit."]
    assert audio["music"]["status"] == "added" and audio["music"]["title"] == "Calme"
    kinds = {c["kind"] for c in render["credits"]}
    assert kinds == {"voice", "music"}

    # Le jeu (tout en « other ») est atténué de 15 dB par rapport à la source.
    workdir = fast_settings.resolve_data_path(f"projects/{pid}/renders/{render['id']}")
    from app.audio import mix

    attenuated = mix.read_audio(workdir / "game_attenuated.wav")
    original = mix.read_audio(
        fast_settings.resolve_data_path(f"sources/{pid}/source.mp4"),
        start=render["start_seconds"],
        duration=render["duration_seconds"],
    )
    assert mix.rms_db(original) - mix.rms_db(attenuated) == pytest.approx(15, abs=1.5)

    # Narration sous-titrée (sans surlignage mot à mot).
    narr_cues = [c for c in render["subtitles"] if not c["karaoke"]]
    assert " ".join(c["text"] for c in narr_cues).startswith("Il lance la partie.")

    # Aperçu audio écoutable.
    assert render["preview_audio_url"]
    assert client.get(render["preview_audio_url"]).status_code == 200

    # Rapport de risques et fiche d'export.
    risk = render["risk_report"]
    assert risk["audio_music"]["status"] == "atténuée"
    assert risk["facecam"]["status"] == "exclu"
    assert any("narration" in a for a in risk["transformation"]["added"])
    assert any("Crédits" in w for w in render["export_warnings"])
    r = client.post(f"/api/renders/{render['id']}/confirm-export", json={"acknowledged": True})
    assert r.status_code == 200, r.text
    sidecar = json.loads(Path(r.json()["exported_path"]).with_suffix(".json").read_text("utf-8"))
    assert {c["kind"] for c in sidecar["credits"]} == {"voice", "music"}
    assert sidecar["audio"]["narration"]["status"] == "added"


def test_phase5_degrades_gracefully_without_models_or_library(
    client: TestClient, fast_settings: Settings, session_factory: sessionmaker[Session], video: Path
) -> None:
    """Sans modèles ni musique : le montage aboutit et le rapport dit ce qui n'a pas été fait."""
    worker = _worker(fast_settings, session_factory, video, FakeEditor(music_mood="calme"), None)
    _, cand = _candidate(client, worker)
    render = _render(client, worker, cand["id"])
    assert render["job_status"] == "completed", render["job_error"]
    assert render["facecam"]["status"] == "unavailable"
    audio = render["audio_report"]
    assert audio["source_music"]["status"] == "unavailable"
    assert audio["narration"]["status"] == "not_needed"
    assert audio["music"]["status"] == "empty_library"
    assert render["credits"] == []
    assert "Musique d'origine non analysée." in render["export_warnings"]
    assert any(w.startswith("Facecam :") for w in render["export_warnings"])
    assert render["preview_audio_url"]
