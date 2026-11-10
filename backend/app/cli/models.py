"""Gestion des modèles locaux.

    python -m app.cli.models status      # modèle configuré, présence, taille
    python -m app.cli.models download    # télécharge le modèle configuré (confirmation demandée)

Le modèle est stocké dans GSA_DATA_DIR/models ; le cache Hugging Face aussi (HF_HOME),
afin de ne rien écrire de volumineux sur le disque système.
"""

from __future__ import annotations

import argparse
import os
import sys

from app.core.config import get_settings

# Tailles indicatives (CTranslate2, Hugging Face) — affichées avant téléchargement.
APPROX_SIZE_GB = {
    "tiny": 0.08,
    "base": 0.15,
    "small": 0.48,
    "medium": 1.5,
    "large-v3": 3.1,
    "large-v3-turbo": 1.6,
    "turbo": 1.6,
}


def _dir_size(path: str) -> int:
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli.models")
    parser.add_argument("action", choices=["status", "download"])
    parser.add_argument("--yes", action="store_true", help="ne pas demander de confirmation")
    args = parser.parse_args(argv)

    settings = get_settings()
    settings.ensure_data_dirs()
    target = settings.whisper_model_dir
    present = (target / "model.bin").is_file()
    print(f"Modèle configuré (GSA_WHISPER_MODEL) : {settings.whisper_model}")
    print(f"Emplacement : {target}")
    if args.action == "status":
        if present:
            print(f"Présent : oui ({_dir_size(str(target)) / 1e9:.2f} Go)")
        else:
            print("Présent : non")
        return 0 if present else 1

    if present:
        print("Déjà présent : rien à faire.")
        return 0
    size = APPROX_SIZE_GB.get(settings.whisper_model)
    print(f"Taille approximative : {size} Go" if size else "Taille : inconnue")
    if not args.yes and input("Télécharger maintenant ? [o/N] ").strip().lower() not in {
        "o",
        "oui",
        "y",
    }:
        print("Annulé.")
        return 1
    os.environ["HF_HOME"] = str(settings.subdir("models") / "hf-cache")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from faster_whisper.utils import download_model

    path = download_model(settings.whisper_model, output_dir=str(target))
    print(f"Téléchargé : {path} ({_dir_size(path) / 1e9:.2f} Go)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
