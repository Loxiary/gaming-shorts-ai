# Benchmark de la transcription locale — 10 novembre 2026

## Mesure de référence : vraie vidéo, GPU libre

Import réel complet via l'application (`ingest_youtube`), Minecraft fermé, VRAM au repos 1,07 Go :

| Élément | Valeur |
|---|---|
| Vidéo | 10 min 33 s, 1920×1080 60 i/s, commentaire en anglais sur du gameplay (Satisfactory) |
| Validation + téléchargement (206 Mo) | 4 s + 30 s |
| ffprobe + extraction audio | < 1 s + 0,6 s |
| Chargement du modèle | 3,3 s |
| **Transcription** | **18,8 s, soit 33,6 × temps réel** (int8_float16, beam 5, VAD, mots horodatés) |
| VRAM | 1 072 → 2 423 Mio (**+1,35 Go**), libérée ensuite |
| Résultat | 118 segments, 1 947 mots horodatés, langue `en` (p = 1,0), 18 mots sous 0,5 de confiance |
| Durée totale du job | ≈ 55 s |

Lecture visuelle de la transcription : fidèle (noms propres, chiffres « 1,200 hour », « 4,000
hours »). Projection : ≈ 2 min de transcription pour 1 h de vidéo avec ce réglage.

## Mesures préliminaires (GPU partagé)

Mesures réelles sur la machine cible (RTX 3060 Ti 8 Go, Ryzen 5 3600, 16 Go).
Outil reproductible : `cd backend; .\.venv\Scripts\python.exe -m app.cli.benchmark_asr <fichier>`.

## ⚠ Conditions de mesure

Pendant toutes les mesures, **un autre programme (Minecraft via Modrinth, `javaw.exe`) occupait
le GPU à 85–98 % (≈ 190 W)**, en plus des applications de bureau (≈ 3,1 Go de VRAM utilisés au
repos). Les **vitesses ci-dessous sont donc pessimistes et instables** (variations ×3 entre deux
exécutions identiques). Elles doivent être refaites jeu fermé avant toute décision de réglage.
Les mesures de **précision** et de **VRAM**, elles, sont fiables.

## Échantillon

- Vidéo synthétique 1280×720, 155,9 s : voix française (synthèse vocale Windows « Hortense »,
  texte de jeu connu de 103 mots × 4) mélangée à un bruit de fond brun (simulation de jeu).
- Limite : une voix de synthèse est plus facile à transcrire qu'une vraie partie (voix
  superposées, cris, musique). **Un essai sur une vraie vidéo reste à faire.**

## Résultats

Modèle `large-v3-turbo` (CTranslate2, 1,62 Go sur disque), VAD activé, horodatage des mots.

| Configuration | Erreurs de mots (WER) | Vitesse (× temps réel)* |
|---|---|---|
| int8_float16, beam 5 (**défaut**) | ≈ 0 % (37 segments, 413 mots, langue fr p=0,9985) | 1,8 – 2,2× |
| float16, beam 5 | 0,26 % | 3,0 – 16,9× |
| float16, beam 1 | 0,00 % | 4,8 – 18,7× |
| int8_float16, beam 1 | 0,26 % | 36,4× |

\* sous charge GPU concurrente, voir l'avertissement ci-dessus.

- **VRAM** : +1,2 à +1,35 Go pendant la transcription (pic 4,4–4,6 Go au total avec le bureau
  et le jeu), entièrement libérée à la fin (vérifié avec `nvidia-smi`).
- **Chargement du modèle** : 8 à 11 s (24 s au tout premier chargement, cache disque froid).
- **Pipeline complet réel** (worker + FFmpeg + GPU, source locale à la place de YouTube) :
  99 s pour 156 s de vidéo, 5 étapes terminées.

## Décision

- Défaut conservé : `int8_float16`, `beam_size=5` (le plus fidèle). GPU libre, il est déjà
  33× plus rapide que le temps réel : inutile de sacrifier de la précision.
- `GSA_WHISPER_BEAM_SIZE=1` reste une option si la transcription doit tourner pendant qu'un jeu
  occupe le GPU.
