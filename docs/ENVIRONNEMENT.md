# Audit de l'environnement — 10 novembre 2026

Relevé effectué sur la machine cible avant la Phase 1 (commandes réellement exécutées).

## Matériel et système

| Élément | Valeur relevée | Remarque |
|---|---|---|
| OS | Windows 11 Famille 10.0.26200, 64 bits | |
| CPU | AMD Ryzen 5 3600 (6 cœurs) | Conforme au cahier des charges |
| RAM | 15,9 Go — **1,8 Go libres** au moment du relevé | Nombreuses applications ouvertes ; à surveiller pour les phases IA |
| GPU | **NVIDIA GeForce RTX 3060 Ti — 8192 Mio de VRAM** | Le cahier des charges indiquait 6 Go : la VRAM réelle est 8 Go |
| VRAM utilisée au repos | 3563 Mio (bureau, navigateurs, Spotify, etc.) | **≈ 4,4 Go réellement libres** |
| Pilote / CUDA | 617.42 / CUDA 13.4, compute capability 8.6 | |
| Disque C: | **31 Go libres** / 476 Go | Insuffisant pour les médias |
| Disque D: | 425 Go libres / 931 Go | **Retenu pour `GSA_DATA_DIR` = `D:\GamingShortsAI\data`** |

Commande GPU : `nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,driver_version,compute_cap --format=csv`

## Logiciels

| Outil | Version | Emplacement |
|---|---|---|
| Python | 3.13.15 (SQLite 3.50.4) | `C:\Program Files\Python313` |
| pip | 26.2.1 | |
| Node.js / npm | 24.18.0 / 11.16.0 | `C:\Program Files\nodejs` |
| Git | 2.55.0 | |
| FFmpeg / ffprobe | 8.1.1 essentials (WinGet, Gyan) | Encodeurs présents : `libx264`, `h264_nvenc`, `hevc_nvenc`, `aac` |
| uv | absent | non requis (venv + pip) |
| Stratégie PowerShell | RemoteSigned (CurrentUser) | scripts lancés avec `-ExecutionPolicy Bypass` |

## Conséquences pour les phases suivantes

1. **Budget VRAM réaliste : 4 à 5 Go** tant que les applications de bureau tournent. Les modèles
   (ASR, vision, LLM local) devront être choisis et mesurés sur cette base, chargés un par un.
2. **Python 3.13** : vérifier en Phase 2 la disponibilité de roues CUDA Windows pour
   faster-whisper/CTranslate2 et PyTorch ; prévoir un environnement 3.12 dédié si nécessaire.
3. **Disque C:** : rediriger aussi vers D: les caches lourds (pip, Hugging Face `HF_HOME`,
   modèles) pour ne pas consommer l'espace système.
4. FFmpeg dispose de NVENC : l'encodage H.264 matériel sera évalué en phase de rendu.
