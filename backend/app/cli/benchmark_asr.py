"""Benchmark reproductible de la transcription locale.

    python -m app.cli.benchmark_asr <fichier audio ou vidéo> [--json rapport.json]

Extrait l'audio (WAV 16 kHz mono) dans GSA_DATA_DIR/temp, transcrit avec la configuration
GSA_WHISPER_* courante, puis affiche : appareil, temps de chargement, temps de traitement,
facteur temps réel, VRAM (avant / pic, toutes applications confondues) et un extrait.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from app.adapters.asr.faster_whisper import FasterWhisperTranscriber
from app.adapters.gpu import query_gpu
from app.adapters.media.ffmpeg import FfmpegTool
from app.core.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli.benchmark_asr")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path, help="écrire le rapport complet en JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    settings.ensure_data_dirs()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    tool = FfmpegTool()
    probe = tool.probe(args.input)
    with tempfile.TemporaryDirectory(dir=settings.subdir("temp")) as tmp:
        wav = Path(tmp) / "audio.wav"
        tool.extract_audio(args.input, wav, probe.duration_seconds, lambda *_: None, lambda: None)
        result = FasterWhisperTranscriber(settings).transcribe(wav, lambda *_: None, lambda: None)

    rtf = (
        result.audio_duration_seconds / result.processing_seconds
        if result.processing_seconds
        else 0
    )
    report = {
        "input": str(args.input),
        "gpu": query_gpu(),
        **result.model_dump(exclude={"segments"}),
        "realtime_factor": round(rtf, 2),
        "segments": len(result.segments),
        "words": sum(len(s.words) for s in result.segments),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\nExtrait :")
    for seg in result.segments[:8]:
        print(f"  [{seg.start:7.2f} → {seg.end:7.2f}] {seg.text}")
    if args.json:
        full = report | {"transcript": [s.model_dump() for s in result.segments]}
        args.json.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
