"""Tests unitaires des adaptateurs (yt-dlp simulé, FFmpeg réel, Whisper sans modèle)."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import pytest
from yt_dlp.utils import DownloadError

from app.adapters.asr.faster_whisper import FasterWhisperTranscriber, load_wav_16k_mono
from app.adapters.downloader import youtube as yt
from app.adapters.media.ffmpeg import FfmpegTool
from app.core.config import Settings
from app.workers.errors import JobCancelled, StepError
from tests.fakes import make_test_video, requires_ffmpeg

# --------------------------------------------------------------------------- yt-dlp


class _FakeYDL:
    info: dict[str, Any] = {}
    error: Exception | None = None
    last_opts: dict[str, Any] = {}

    def __init__(self, opts: dict[str, Any]) -> None:
        _FakeYDL.last_opts = opts

    def __enter__(self) -> _FakeYDL:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def extract_info(self, url: str, download: bool) -> dict[str, Any]:
        if _FakeYDL.error:
            raise _FakeYDL.error
        return _FakeYDL.info


@pytest.fixture
def fake_ydl(monkeypatch: pytest.MonkeyPatch) -> type[_FakeYDL]:
    _FakeYDL.info, _FakeYDL.error = {}, None
    monkeypatch.setattr(yt.yt_dlp, "YoutubeDL", _FakeYDL)
    return _FakeYDL


def _info(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "abcdefghijk",
        "title": "Ma partie",
        "uploader": "Moi",
        "duration": 600,
        "license": "Creative Commons Attribution license (reuse allowed)",
        "live_status": "not_live",
        "availability": "public",
        "upload_date": "20261101",
        "requested_formats": [{"filesize": 50_000_000}, {"filesize_approx": 5_000_000}],
        "formats": ["énorme liste non conservée"],
    }
    return base | overrides


def test_metadata_ok_and_safe_options(fake_ydl: type[_FakeYDL], settings: Settings) -> None:
    fake_ydl.info = _info()
    meta = yt.YouTubeDownloader(settings).fetch_metadata("https://www.youtube.com/watch?v=x")
    assert meta.title == "Ma partie"
    assert meta.estimated_size_bytes == 55_000_000
    assert meta.platform_license.startswith("Creative Commons")
    assert "formats" not in meta.raw
    opts = fake_ydl.last_opts
    assert opts["noplaylist"] is True
    assert opts["cookiefile"] is None
    assert "height<=1080" in opts["format"]
    assert opts["format"].startswith("bv*[height<=1080][vcodec^=avc1]")
    assert opts["js_runtimes"] == {"node": {}}


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"_type": "playlist"}, "playlist"),
        ({"live_status": "is_live"}, "direct"),
        ({"live_status": "is_upcoming"}, "direct"),
        ({"availability": "subscriber_only"}, "compte"),
        ({"requested_formats": [{"has_drm": True}]}, "DRM"),
        ({"duration": 300 * 60}, "trop longue"),
    ],
)
def test_metadata_rejections(
    fake_ydl: type[_FakeYDL], settings: Settings, overrides: dict[str, Any], fragment: str
) -> None:
    fake_ydl.info = _info(**overrides)
    with pytest.raises(StepError) as exc:
        yt.YouTubeDownloader(settings).fetch_metadata("https://www.youtube.com/watch?v=x")
    assert fragment in exc.value.message


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("ERROR: [youtube] x: Private video. Sign in if you've been granted access", "privée"),
        ("ERROR: [youtube] x: Sign in to confirm your age", "restriction d'âge"),
        ("ERROR: [youtube] x: Sign in to confirm you're not a bot", "ne contourne pas"),
        ("ERROR: [youtube] x: Video unavailable", "indisponible"),
        ("ERROR: something new", "Échec yt-dlp : something new"),
    ],
)
def test_download_errors_are_translated(
    fake_ydl: type[_FakeYDL], settings: Settings, raw: str, fragment: str
) -> None:
    fake_ydl.error = DownloadError(raw)
    with pytest.raises(StepError) as exc:
        yt.YouTubeDownloader(settings).fetch_metadata("https://www.youtube.com/watch?v=x")
    assert fragment in exc.value.message
    assert exc.value.technical == raw


# --------------------------------------------------------------------------- FFmpeg


@requires_ffmpeg
def test_probe_and_extract_audio(tmp_path: Path) -> None:
    video = make_test_video(tmp_path / "v.mp4", 2.0)
    tool = FfmpegTool()
    probe = tool.probe(video)
    assert probe.has_video and probe.has_audio
    assert (probe.width, probe.height, probe.fps) == (320, 240, 30.0)
    assert 1.8 < probe.duration_seconds < 2.3

    progress: list[float] = []
    wav = tmp_path / "out" / "audio.wav"
    tool.extract_audio(
        video, wav, probe.duration_seconds, lambda f, _d: progress.append(f), lambda: None
    )
    assert progress[-1] == 1.0
    audio = load_wav_16k_mono(wav)
    assert abs(len(audio) / 16000 - 2.0) < 0.15
    assert not (tmp_path / "out" / "audio.tmp.wav").exists()


@requires_ffmpeg
def test_extract_audio_cancellation_leaves_no_file(tmp_path: Path) -> None:
    video = make_test_video(tmp_path / "v.mp4", 2.0)

    def cancel() -> None:
        raise JobCancelled()

    wav = tmp_path / "audio.wav"
    with pytest.raises(JobCancelled):
        FfmpegTool().extract_audio(video, wav, 2.0, lambda *_: None, cancel)
    assert not wav.exists()
    assert not (tmp_path / "audio.tmp.wav").exists()


@requires_ffmpeg
def test_probe_rejects_corrupt_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"pas une video")
    with pytest.raises(StepError) as exc:
        FfmpegTool().probe(bad)
    assert "ffprobe" in exc.value.message


# --------------------------------------------------------------------------- Whisper


def test_wav_loader_validates_format(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00" * 200)
    with pytest.raises(StepError) as exc:
        load_wav_16k_mono(path)
    assert "16 kHz" in exc.value.message


def test_missing_model_gives_download_instructions(tmp_path: Path, settings: Settings) -> None:
    with pytest.raises(StepError) as exc:
        FasterWhisperTranscriber(settings).transcribe(
            tmp_path / "a.wav", lambda *_: None, lambda: None
        )
    assert "app.cli.models download" in exc.value.message
