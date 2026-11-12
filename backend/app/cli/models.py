"""Gestion des modèles locaux (tous stockés dans GSA_DATA_DIR/models).

    python -m app.cli.models status                 # présence, taille, licence de chaque modèle
    python -m app.cli.models download whisper        # modèle de transcription configuré
    python -m app.cli.models download fr_FR-siwis-medium htdemucs cnn14-16k yunet
    python -m app.cli.models download --all          # tout (taille totale affichée avant)

Une confirmation est demandée avant tout téléchargement (sauf --yes). Les caches de
Hugging Face et de PyTorch sont redirigés vers GSA_DATA_DIR/models (rien sur C:).
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

from app.core.config import Settings, get_settings
from app.models_registry import ALL_ASSETS, ModelAsset

WHISPER_SIZES_GB = {
    "tiny": 0.08,
    "base": 0.15,
    "small": 0.48,
    "medium": 1.5,
    "large-v3": 3.1,
    "large-v3-turbo": 1.6,
    "turbo": 1.6,
}


def asset_dir(settings: Settings, asset: ModelAsset) -> Path:
    return settings.subdir("models") / asset.subdir


def asset_present(settings: Settings, asset: ModelAsset) -> bool:
    d = asset_dir(settings, asset)
    return all((d / name).is_file() and (d / name).stat().st_size > 0 for name in asset.files)


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "gaming-shorts-ai/0.5"})
    with urllib.request.urlopen(req, timeout=60) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r    {dest.name} : {done / 1e6:.0f} / {total / 1e6:.0f} Mo", end="")
    print()
    if tmp.stat().st_size == 0:
        tmp.unlink()
        raise RuntimeError(f"Téléchargement vide : {url}")
    tmp.replace(dest)


def download_asset(settings: Settings, asset: ModelAsset) -> None:
    d = asset_dir(settings, asset)
    for name, url in asset.files.items():
        if not (d / name).is_file():
            _download(url, d / name)


def _whisper_status(settings: Settings) -> tuple[bool, str]:
    target = settings.whisper_model_dir
    present = (target / "model.bin").is_file()
    return present, f"{_dir_size(target) / 1e9:.2f} Go" if present else "absent"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m app.cli.models")
    parser.add_argument("action", choices=["status", "download"])
    parser.add_argument("ids", nargs="*", help="whisper et/ou identifiants du catalogue")
    parser.add_argument("--all", action="store_true", help="télécharger tous les modèles")
    parser.add_argument("--yes", action="store_true", help="ne pas demander de confirmation")
    args = parser.parse_args(argv)

    settings = get_settings()
    settings.ensure_data_dirs()
    os.environ["HF_HOME"] = str(settings.subdir("models") / "hf-cache")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    w_present, w_info = _whisper_status(settings)
    if args.action == "status":
        print(f"Dossier des modèles : {settings.subdir('models')}")
        print(f"- whisper ({settings.whisper_model}) : {w_info}")
        for asset in ALL_ASSETS.values():
            state = "présent" if asset_present(settings, asset) else "absent"
            print(
                f"- {asset.id} : {state} — {asset.label} — ~{asset.size_mb:g} Mo — {asset.license}"
            )
        missing = [a.id for a in ALL_ASSETS.values() if not asset_present(settings, a)]
        return 0 if w_present and not missing else 1

    wanted = list(ALL_ASSETS) + ["whisper"] if args.all else args.ids
    unknown = [i for i in wanted if i != "whisper" and i not in ALL_ASSETS]
    if not wanted or unknown:
        print(f"Identifiants inconnus ou absents : {unknown or '(aucun)'}")
        print(f"Disponibles : whisper, {', '.join(ALL_ASSETS)}")
        return 2
    todo = [
        i
        for i in wanted
        if (i == "whisper" and not w_present)
        or (i != "whisper" and not asset_present(settings, ALL_ASSETS[i]))
    ]
    if not todo:
        print("Tout est déjà présent : rien à faire.")
        return 0
    total = 0.0
    for i in todo:
        if i == "whisper":
            size = WHISPER_SIZES_GB.get(settings.whisper_model, 0) * 1000
            print(f"- whisper ({settings.whisper_model}) : ~{size:g} Mo — MIT")
        else:
            a = ALL_ASSETS[i]
            size = a.size_mb
            print(f"- {a.id} : ~{a.size_mb:g} Mo — {a.license}")
        total += size
    print(f"Total : ~{total:.0f} Mo dans {settings.subdir('models')}")
    if not args.yes and input("Télécharger maintenant ? [o/N] ").strip().lower() not in {
        "o",
        "oui",
        "y",
    }:
        print("Annulé.")
        return 1
    for i in todo:
        if i == "whisper":
            from faster_whisper.utils import download_model

            download_model(settings.whisper_model, output_dir=str(settings.whisper_model_dir))
        else:
            download_asset(settings, ALL_ASSETS[i])
        print(f"OK : {i}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
