"""Relevés GPU via nvidia-smi (arguments fixes). Sans GPU NVIDIA, les fonctions renvoient None."""

from __future__ import annotations

import shutil
import subprocess
import threading

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_QUERY = "name,memory.total,memory.used,memory.free,driver_version"


def query_gpu() -> dict[str, object] | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, f"--query-gpu={_QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = proc.stdout.strip().splitlines()[0] if proc.returncode == 0 and proc.stdout else ""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != 5:
        return None
    name, total, used, free, driver = parts
    try:
        return {
            "name": name,
            "memory_total_mib": int(total),
            "memory_used_mib": int(used),
            "memory_free_mib": int(free),
            "driver_version": driver,
        }
    except ValueError:
        return None


class GpuMemorySampler:
    """Échantillonne la VRAM utilisée (toutes applications confondues) pendant un traitement."""

    def __init__(self, interval: float = 1.0) -> None:
        self.interval = interval
        self.baseline: int | None = None
        self.peak: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> int | None:
        info = query_gpu()
        return int(info["memory_used_mib"]) if info else None  # type: ignore[arg-type]

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            used = self._sample()
            if used is not None:
                self.peak = max(self.peak or 0, used)

    def __enter__(self) -> GpuMemorySampler:
        self.baseline = self._sample()
        self.peak = self.baseline
        if self.baseline is not None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
