# Gaming Shorts AI

Application locale (Windows 11) destinée à transformer des vidéos longues de gameplay en shorts verticaux.

> **État actuel : Phase 5 — audio et facecam.** L'application importe des vidéos YouTube, les
> transcrit en local, détecte et note les meilleurs extraits (61–180 s), puis **monte des shorts
> verticaux 1080×1920 H.264/AAC** (fond flouté, sous-titres animés mot à mot ou traduits,
> accroche, appel à l'action, zooms). En local et sans coût supplémentaire, elle **détecte et
> atténue la musique d'origine** (voix conservées), ajoute si l'IA la juge utile une **narration
> de synthèse factuelle**, une **musique de votre bibliothèque sous licence**, et **exclut un
> facecam** par recadrage. Chaque short est **contrôlé**, accompagné d'un **rapport de risques
> informatif** avec les crédits à publier, et **n'est exporté qu'après votre confirmation**.

Documents de référence (racine du dépôt) : `CAHIER_DES_CHARGES.md`, `ARCHITECTURE_TECHNIQUE.md`,
`CLAUDE_INSTRUCTIONS.md`, `PROMPT_INITIAL_CLAUDE_CODE.txt`. Audit machine : `docs/ENVIRONNEMENT.md`.
Mesures de transcription : `docs/BENCHMARK_ASR.md`.

## Architecture

```text
Navigateur ──► Frontend React/TS (Vite, 127.0.0.1:5173)
                   │  /api (proxy Vite)
                   ▼
              API FastAPI (127.0.0.1:8000) ──► SQLite (GSA_DATA_DIR\gaming_shorts.db, WAL)
                                                   ▲
              Worker (processus séparé) ───────────┘  réclame les jobs un par un
```

- **Backend** (`backend/app`) : `core/` (config, logs JSON, erreurs), `models/` (Project, Job,
  JobStep, WorkerHeartbeat, SourceMedia, Transcript, TranscriptSegment), `db/` (moteur,
  migrations), `services/` (projets, import, sources, file d'attente), `api/` (routes),
  `workers/` (boucle du worker, contexte d'étape, pipeline d'ingestion, jobs de démo),
  `adapters/` (interfaces remplaçables : `downloader/youtube.py` yt-dlp, `media/ffmpeg.py`,
  `asr/faster_whisper.py`, `gpu.py`), `cli/` (modèles, benchmark).
- **Migrations** : Alembic (`backend/alembic/versions`).
- **Frontend** (`frontend/src`) : `services/` (client API typé, hooks TanStack Query),
  `components/`, `features/{dashboard,projects,queue,settings}`.

### File d'attente persistante

- Statuts de job : `queued`, `running`, `completed`, `failed`, `cancelled` ; chaque étape
  (`job_steps`) a son propre statut.
- Réclamation atomique (`UPDATE … WHERE status='queued' RETURNING`) : deux workers ne prennent
  jamais le même job. Traitement séquentiel (un job à la fois).
- Anti-doublon : un seul job actif (en attente/en cours) d'un même type par projet (index unique
  partiel SQLite).
- **Reprise** : un job « running » dont le worker ne donne plus signe de vie depuis
  `GSA_WORKER_STALE_SECONDS` (30 s) est remis en file ; les étapes terminées ne sont jamais
  rejouées. Une relance (`retry`) d'un job échoué/annulé repart de la première étape non terminée.
- **Annulation** : immédiate si le job attend, sinon à la fin de l'étape en cours.
- Suivi de la progression par interrogation périodique (2 s) ; SSE/WebSocket envisageables plus tard.
  Chaque étape publie sa progression et un détail lisible (ex. « 45 Mo / 120 Mo »).
- **Annulation pendant une étape longue** (téléchargement, extraction audio, transcription) à des
  points d'arrêt sûrs ; un fichier partiel n'est jamais enregistré sous son nom définitif.

### Pipeline d'ingestion (`ingest_youtube`)

| Étape | Rôle | Sortie |
|---|---|---|
| `validating_source` | Métadonnées yt-dlp ; refus explicite des playlists, directs, vidéos privées / réservées à un compte / soumises à l'âge / DRM, vidéos trop longues ; contrôle de l'espace disque | titre, créateur, licence annoncée, durée |
| `downloading` | yt-dlp, ≤ 1080p, H.264 privilégié, MP4, reprise des fichiers partiels, sans cookies ni identifiants | `sources/<projet>/source.mp4` |
| `probing_media` | ffprobe : résolution, i/s, codecs, durée réelle, présence d'audio | colonnes `source_media` |
| `extracting_audio` | FFmpeg → WAV PCM 16 kHz mono (écriture atomique) | `projects/<projet>/audio_16k_mono.wav` |
| `transcribing` | faster-whisper local (GPU si dispo, repli CPU signalé), VAD, mots horodatés | `transcripts` + `transcript_segments` |

Les étapes sont idempotentes : à la reprise, un fichier déjà complet est réutilisé. Chaque étape
enregistre sa sortie (mesures, versions, chemins) dans `job_steps.output_json` (provenance).
La transcription produite est la **transcription source verbatim** (`kind = "source"`) ; les
futures traductions seront stockées séparément.

### Pipeline d'analyse (`analyze_clips`)

Lancé depuis la fiche d'un projet (profil + mode d'évaluation). L'analyse n'envoie jamais la
vidéo entière à une API : seulement l'extrait de transcription, un résumé des signaux et quelques
images réduites de chaque candidat.

| Étape | Rôle |
|---|---|
| `preparing_proxy` | Copie légère H.264 480p 10 i/s (décodage AV1 matériel NVIDIA si possible), réutilisée |
| `detecting_scenes` | Changements de scène (filtre FFmpeg `scdet`), stockés par source et réutilisés |
| `analyzing_audio` | Énergie sonore relative, débit de parole, densité de coupes → courbe d'« intérêt » par seconde |
| `generating_candidates` | Fenêtres de 61 à 180 s (bornes du profil) autour des pics, calées en priorité sur des **phrases complètes** (ponctuation des mots horodatés), doublons éliminés ; vidéo trop courte → aucun extrait, avec une note |
| `sampling_frames` | ~8 images horodatées par extrait (début, pics d'intérêt et sonores, répartition) |
| `scoring_candidates` | **IA** (Claude Sonnet 5.5, sortie JSON validée, une relance si invalide) ou **signaux seuls** (gratuit, confiance 25 %, clairement signalé). Un extrait déjà évalué n'est jamais renvoyé à l'IA lors d'une reprise |
| `selecting_clips` | Note globale = moyenne pondérée (profil) ×10 ; seuil ; chevauchements > 30 % retirés |

**Critères (0–10)** : force de l'accroche, divertissement / intensité, compréhension autonome,
progression narrative, potentiel de rétention, originalité / valeur ajoutée, qualité
audio-visuelle. Chaque note est justifiée ; les notes sont des estimations, pas des prédictions
de vues. Le seuil peut être changé après coup (« Appliquer le seuil ») sans nouvel appel payant.

**Coûts** : le plafond mensuel (40 $ par défaut, modifiable dans Paramètres) est vérifié
**avant chaque appel** avec une estimation haute (jetons comptés + sortie maximale). S'il est
atteint en cours d'analyse, les extraits restants sont évalués par signaux et une note
l'indique. Chaque appel est journalisé (jetons, images, coût, identifiant de requête) dans
« Coûts API ». Sur une vidéo de 10 min, l'estimation est d'environ 0,30 $ (12 extraits).

**Profils** : 5 profils d'exemple (GTA 6 — Viral / Humour / Action, Gaming — Immersion /
Histoire), modifiables, duplicables, supprimables (sauf le profil par défaut). Chaque analyse
garde une copie des réglages du profil utilisé.

### Montage d'un short (`render_clip`)

Lancé par « Monter ce clip » sur un extrait évalué. Plusieurs montages peuvent attendre dans la
file ; un même extrait ne peut pas être monté deux fois en parallèle.

| Étape | Rôle |
|---|---|
| `creating_editorial_plan` | IA : accroche (≤ 60 car., « citation » vérifiée mot pour mot dans la transcription, sinon « texte original » signalé), appel à l'action, mots clés, 0 à 3 zooms sur des moments réels ; **narration** (seulement si utile : 1 à 4 lignes factuelles, placées dans les silences) et **ambiance musicale**. Sans IA ou plafond atteint : plan de repli (citation réelle, zooms sur les pics sonores, jamais de narration), signalé |
| `detecting_facecam` | 10 images de l'extrait, détecteur de visages YuNet (position seulement, aucune reconnaissance d'identité). Un visage **au même endroit, près d'un bord, sur ≥ 50 % des images** = facecam : recadrage du côté qui retire le moins d'image (avertissement au-delà de 35 %). Cas douteux (25–50 %, visage central) : signalé, sans recadrage |
| `preparing_audio` | Musique d'origine détectée seconde par seconde (PANNs CNN14, classe « Music »), puis atténuée par **séparation de sources** (Demucs htdemucs, processeur) : voix intactes, autres sources baissées de N dB pendant la musique, musique résiduelle re-mesurée. Narration Piper (voix du profil, langue vérifiée), décalée dans un silence si elle couvre la parole, sinon abandonnée. Musique de la bibliothèque (licence confirmée uniquement), bouclée, avec fondus. Ducking calé sur les horodatages connus (parole, narration). Aperçu audio AAC au niveau final, écoutable dès cette étape |
| `preparing_subtitles` | Sous-titres ASS : 1 à 6 mots par groupe, mot prononcé surligné, mots clés en couleur ; la narration ajoutée est aussi sous-titrée. Mode « traduire » : traduction IA phrase par phrase, **stockée à part et affichée comme traduction** (la transcription source n'est jamais modifiée) |
| `rendering` | FFmpeg : recadrage facecam éventuel, gameplay centré sur fond flouté (ou plein cadre), zooms, accroche (3 premières s) et appel à l'action (4 dernières s) en haut de l'écran, piste mixée normalisée à -14 LUFS, H.264/AAC (libx264 ou NVENC) |
| `quality_check` | Fichier réellement produit : présence, **durée 61–180 s**, 1080×1920, H.264, yuv420p, AAC, lecture complète sans erreur (critiques) ; durée attendue, synchronisation A/V, cadence, volume, saturation (avertissements) |
| `building_risk_report` | Source et créateur, droits déclarés, transformation éditoriale (narration et musique comprises), risque de « contenu réutilisé », musique d'origine (absente / atténuée / encore détectable / conservée / non analysée), facecam (exclu / absent / incertain / non vérifié), **crédits à publier** (voix CC BY, musique), avertissements de l'IA, recommandations — **jamais bloquant** |

Un modèle absent ne fait jamais échouer le montage : la fonction est sautée et le rapport le dit.

**Export** : uniquement après confirmation (case « J'ai lu ces avertissements »). Le MP4 est copié
dans `GSA_DATA_DIR\exports` avec une fiche JSON (source, droits, audio, facecam, **crédits**,
contrôle qualité, rapport de risques, avertissements acceptés). Les risques ne bloquent jamais l'export ; seul un fichier
techniquement invalide (contrôle critique échoué) ne peut pas être exporté. Supprimer un rendu
ou un projet **conserve** les fichiers exportés.

**Coût réel mesuré** : environ 0,01 à 0,02 $ par short (plan éditorial + traduction éventuelle
des sous-titres) ; l'audio et le facecam sont locaux et gratuits. Short de 68 s en 1080×1920 à
60 i/s : 113 s au total, dont 32 s de séparation de la musique sur le processeur.

### Bibliothèque musicale

L'application **ne télécharge aucune musique**. Déposez vos morceaux (mp3, wav, flac, ogg, m4a,
opus) dans `GSA_DATA_DIR\music`, cliquez « Analyser le dossier » (page Musique), puis pour chaque
morceau renseignez titre, artiste, **licence**, source, ambiances, et cochez la confirmation
d'autorisation. Seuls ces morceaux sont choisis (selon l'ambiance proposée par l'IA) et leur
crédit est ajouté au rapport et à la fiche d'export. Aucune musique n'est ajoutée par-dessus une
musique d'origine conservée.

### Droits

Le statut des droits (inconnu / créateur / autorisation / licence) est une **déclaration de
l'utilisateur**, conservée pour le futur rapport de risques. **Il ne bloque jamais aucun
traitement.** L'application ne contourne aucune restriction technique (compte, âge, DRM,
géoblocage, protection anti-robot) : ces cas échouent avec un message explicite.

### API

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/health` | État API, base (migrée ?) et worker |
| GET | `/api/system` | Configuration, dossiers de données, disque, outils détectés |
| GET/POST | `/api/projects` | Lister / créer |
| GET/PATCH | `/api/projects/{id}` | Détail (avec jobs) / modifier |
| DELETE | `/api/projects/{id}?confirm=true` | Supprimer (confirmation obligatoire ; refusé si un job tourne) |
| GET | `/api/job-kinds` | Types de jobs disponibles (démo uniquement) |
| GET/POST | `/api/jobs` | Lister (`?status=`, `?project_id=`) / ajouter à la file |
| GET | `/api/jobs/{id}` | Détail avec étapes |
| POST | `/api/jobs/{id}/cancel`, `/api/jobs/{id}/retry` | Annuler / relancer |
| POST | `/api/imports` | Importer 1 à 20 liens (résultat par lien : créé / doublon / refusé) |
| PATCH | `/api/projects/{id}/source` | Modifier la déclaration de droits |
| GET | `/api/projects/{id}/transcript` | Transcription source avec segments et mots horodatés |
| GET | `/api/projects/{id}/media` | Vidéo source (lecture locale, requêtes Range) |
| GET/POST | `/api/profiles`, PUT/DELETE `/api/profiles/{id}`, POST `/api/profiles/{id}/duplicate` | Profils de montage |
| GET | `/api/criteria` | Critères de notation |
| GET | `/api/projects/{id}/analysis-estimate` | Estimation du coût IA (aucun appel payant) |
| GET/POST | `/api/projects/{id}/analyses` | Lister / lancer une analyse (`profile_id`, `engine` : auto / llm / signals) |
| GET | `/api/analyses/{id}` | Analyse avec extraits, notes, explications, images |
| POST | `/api/analyses/{id}/reselect` | Nouveau seuil, sélection recalculée sans IA |
| GET | `/api/candidates/{id}/frames/{n}` | Image horodatée d'un extrait |
| GET/PATCH | `/api/settings/api` | Clé configurée (oui/non, jamais la valeur), API activée, plafond |
| GET | `/api/costs` | Dépenses du mois, par mois, derniers appels |
| POST | `/api/candidates/{id}/renders` | Monter un extrait (profil facultatif) |
| GET | `/api/projects/{id}/renders`, `/api/renders/{id}` | Rendus : plan, sous-titres, QC, rapport de risques, avertissements d'export |
| GET | `/api/renders/{id}/video` | Short rendu (lecture, requêtes Range) |
| POST | `/api/renders/{id}/confirm-export` | Export après confirmation (`acknowledged: true` obligatoire) |
| DELETE | `/api/renders/{id}?confirm=true` | Supprimer un rendu (le fichier exporté est conservé) |
| GET | `/api/exports` | Shorts exportés |
| GET | `/api/renders/{id}/audio-preview` | Aperçu du mixage audio (AAC, niveau final) |
| GET | `/api/music`, POST `/api/music/scan` | Bibliothèque musicale / analyse du dossier `music` |
| PATCH | `/api/music/{id}` | Titre, artiste, licence, source, ambiances, confirmation d'autorisation |
| GET | `/api/music/{id}/audio` | Écoute d'un morceau |
| GET | `/api/audio/status` | Modèles audio/facecam et voix installés, ambiances |

Documentation interactive : http://127.0.0.1:8000/docs (quand l'API tourne).

## Prérequis

| Outil | Version validée | Installation |
|---|---|---|
| Windows 11 | 10.0.26200 | — |
| Python | 3.13.15 (≥ 3.12 requis) | https://www.python.org/downloads/windows/ (cocher « Add to PATH ») |
| Node.js / npm | 24.18.0 / 11.16.0 | https://nodejs.org (LTS) |
| FFmpeg / ffprobe | 8.1.1 | `winget install Gyan.FFmpeg.Essentials` (analyse et extraction audio) |
| GPU NVIDIA (facultatif) | pilote ≥ 525 (validé : 617.42) | Sans GPU, la transcription passe sur CPU (beaucoup plus lente) |

Aucune clé API ni Docker. Les bibliothèques CUDA/cuDNN sont installées par pip dans
`backend\.venv` (≈ 2,2 Go sur le disque du projet) : **pas besoin du CUDA Toolkit**.

### Modèle de transcription

Le pipeline ne télécharge **jamais** de modèle automatiquement. Téléchargement explicite
(taille affichée et confirmation demandée), dans `GSA_DATA_DIR\models` :

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.cli.models status
.\.venv\Scripts\python.exe -m app.cli.models download   # large-v3-turbo ≈ 1,6 Go
```

### Modèles audio et facecam (Phase 5)

Même principe : rien n'est téléchargé par le pipeline, `status` affiche taille et licence.

```powershell
.\.venv\Scripts\python.exe -m app.cli.models download --all   # ≈ 540 Mo au total
```

| Modèle | Rôle | Taille | Licence |
|---|---|---|---|
| `fr_FR-siwis-medium` | Voix française (Piper) | 63 Mo | CC BY 4.0 — **crédit ajouté automatiquement** |
| `en_US-joe-medium` | Voix anglaise (Piper) | 63 Mo | CC0 |
| `cnn14-16k` | Détection de musique (PANNs) | 327 Mo | code MIT, poids CC BY 4.0 |
| `htdemucs` | Séparation de sources (Demucs v4) | 84 Mo | MIT |
| `yunet` | Détection de visages (OpenCV Zoo) | 0,3 Mo | MIT |

Les voix Piper dont la licence interdit l'usage commercial ou impose des conditions incertaines
(ex. `ryan` NC, `tom` AGPL, `lessac` et ses dérivées) ne sont pas proposées. Les poids PyTorch
sont chargés en **mode sûr** (`weights_only=True`, types autorisés listés) : aucun code
contenu dans un fichier de modèle n'est exécuté. PyTorch est installé en version processeur
(≈ 0,8 Go).

## Installation

Depuis la racine du dépôt, dans PowerShell :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-env.ps1   # diagnostic (facultatif)
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

`install.ps1` : crée `.env` depuis `.env.example` s'il n'existe pas, crée `backend\.venv` et
installe `backend\requirements-dev.txt`, exécute `npm ci` dans `frontend\`, applique les migrations.

### Configuration (`.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `GSA_DATA_DIR` | `D:\GamingShortsAI\data` | Données locales : base, `sources`, `temp`, `projects`, `exports`, `logs` |
| `GSA_API_HOST` / `GSA_API_PORT` | `127.0.0.1` / `8000` | L'hôte doit rester une adresse de boucle locale (refusé sinon) |
| `GSA_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Origines autorisées |
| `GSA_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `GSA_WORKER_POLL_SECONDS` | `1.0` | Intervalle de scrutation de la file |
| `GSA_WORKER_STALE_SECONDS` | `30` | Délai avant reprise d'un job abandonné |
| `GSA_DEMO_STEP_SECONDS` | `2.0` | Durée simulée d'une étape de démo |
| `GSA_MAX_DOWNLOAD_HEIGHT` | `1080` | Résolution maximale téléchargée |
| `GSA_MAX_SOURCE_MINUTES` | `240` | Durée maximale d'une vidéo importée |
| `GSA_MIN_FREE_DISK_GB` | `5` | Espace disque à conserver en plus de la vidéo |
| `GSA_YTDLP_JS_RUNTIME` | `node` | Moteur JavaScript utilisé par yt-dlp pour YouTube |
| `GSA_WHISPER_MODEL` | `large-v3-turbo` | Modèle faster-whisper (dossier `models\faster-whisper-<modèle>`) |
| `GSA_WHISPER_DEVICE` | `auto` | `auto`, `cuda` ou `cpu` |
| `GSA_WHISPER_COMPUTE_TYPE` | `auto` | `auto` (int8_float16 GPU / int8 CPU), `float16`, `int8`… |
| `GSA_WHISPER_LANGUAGE` | *(vide)* | Code langue forcé (`fr`, `en`…) ; vide = détection automatique |
| `GSA_WHISPER_VAD` | `true` | Filtre de voix (réduit les hallucinations sur musique/bruit) |
| `GSA_WHISPER_BEAM_SIZE` | `5` | 5 = plus fidèle, 1 = plus rapide (voir `docs/BENCHMARK_ASR.md`) |

| `ANTHROPIC_API_KEY` | *(absente)* | Clé API Claude (dans `.env` uniquement). Sans clé : mode « signaux seuls » |
| `GSA_LLM_MODEL` | `claude-sonnet-5-5` | Modèle d'évaluation des extraits |
| `GSA_LLM_EFFORT` | `medium` | `low`, `medium`, `high` |
| `GSA_LLM_PRICE_*_PER_MTOK` | 2 / 10 / 0,10 / 2,50 | Tarifs ($/million de jetons) pour l'estimation et le suivi |
| `GSA_DEFAULT_MONTHLY_CAP_USD` | `40` | Plafond initial (ensuite réglé dans Paramètres) |
| `GSA_ANALYSIS_PROXY_HEIGHT` | `480` | Hauteur de la copie d'analyse |
| `GSA_FRAMES_PER_CANDIDATE` | `8` | Images envoyées à l'IA par extrait (0 = aucune) |
| `GSA_RENDER_X264_PRESET` | `faster` | Preset x264 du rendu (`ultrafast` … `slow`) |

Les réglages de montage (sous-titres, police, couleurs, disposition, zooms, accroche, appel à
l'action, encodeur) se font **par profil**, dans la page Profils.

Les variables absentes de `.env` prennent la valeur par défaut ci-dessus.

#### Clé API Anthropic

1. Créer une clé sur https://console.anthropic.com (compte et moyen de paiement à votre nom).
2. Ajouter dans `.env` (jamais ailleurs) : `ANTHROPIC_API_KEY=sk-ant-…`
3. Redémarrer : `scripts\stop.ps1` puis `scripts\start.ps1`. Paramètres doit afficher
   « Clé API : Configurée ». La valeur n'est jamais affichée ni journalisée.

## Lancement / arrêt

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Open
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
```

`start.ps1` applique les migrations, lance l'API, le worker et le frontend en arrière-plan
(PID dans `.run\pids.json`, sorties console dans `.run\*.log`), attend qu'ils répondent puis
affiche l'URL : **http://127.0.0.1:5173/**.

Lancement manuel (trois terminaux, pour le développement) :

```powershell
cd backend; .\.venv\Scripts\python.exe -m app.db.migrate; .\.venv\Scripts\python.exe -m app.server
cd backend; .\.venv\Scripts\python.exe -m app.workers.runner
cd frontend; npm run dev
```

## Tests et qualité

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest           # unitaires, API, file, reprise, pipeline (FFmpeg réel)
.\.venv\Scripts\python.exe -m app.cli.benchmark_asr <vidéo>   # mesure réelle GPU (manuel)
.\.venv\Scripts\ruff.exe check .               # lint
.\.venv\Scripts\ruff.exe format --check .      # formatage

cd ..\frontend
npm test                # Vitest + Testing Library
npm run typecheck       # TypeScript strict
npm run lint            # ESLint
npm run format:check    # Prettier
npm run build           # build de production
```

Les tests backend utilisent un dossier de données temporaire : ils ne touchent jamais `GSA_DATA_DIR`.
yt-dlp, le modèle Whisper, l'IA et les modèles audio/facecam (PANNs, Demucs, Piper, YuNet) y
sont remplacés par des faux (aucun accès réseau, aucun téléchargement, aucun appel payant) ;
FFmpeg et ffprobe sont réels (vidéos et musiques synthétiques générées pendant les tests).

## Données et confidentialité

- Tout est stocké localement dans `GSA_DATA_DIR` ; aucune vidéo ni transcription n'est envoyée
  sur Internet (seul yt-dlp contacte YouTube pour télécharger la vidéo demandée).
- `data/`, bases SQLite, médias, modèles, `.env` et `.run/` sont exclus de Git (`.gitignore`).
- Logs JSON structurés : `GSA_DATA_DIR\logs\api.log`, `worker.log`, `migrate.log` (rotation 5 Mo × 3).
- La suppression d'un projet demande une confirmation (taille des fichiers affichée) et efface
  ses jobs, sa source, sa transcription et ses dossiers `sources\<projet>` et `projects\<projet>`.

## Dépannage

| Symptôme | Cause / solution |
|---|---|
| « Backend injoignable » dans l'interface | L'API ne tourne pas : `scripts\start.ps1`, puis voir `.run\api.out.log` |
| « Worker arrêté » / jobs bloqués « En attente » | Le worker ne tourne pas : `scripts\stop.ps1` puis `scripts\start.ps1` ; voir `.run\worker.out.log` |
| Job resté « En cours » après un crash | Normal : il est repris automatiquement ≤ 30 s après le redémarrage du worker |
| « Base non migrée » / erreur 503 `database_not_ready` | `cd backend; .\.venv\Scripts\python.exe -m app.db.migrate` |
| `Le port 8000 (ou 5173) est deja utilise` | Une instance tourne déjà (`scripts\stop.ps1`) ou un autre programme occupe le port |
| `L'application semble deja lancee` | `scripts\stop.ps1` puis relancer |
| Scripts bloqués par la stratégie d'exécution | Toujours lancer avec `powershell -ExecutionPolicy Bypass -File …` |
| Accents illisibles dans les logs avec `Get-Content` (PowerShell 5.1) | Les logs sont en UTF-8 : `Get-Content -Encoding UTF8 …` |
| « Modèle de transcription absent » | `cd backend; .\.venv\Scripts\python.exe -m app.cli.models download` |
| « GPU indisponible … transcription sur CPU » | Pilote NVIDIA absent/obsolète ou VRAM saturée (jeu en cours) ; fermer les applications GPU ou forcer `GSA_WHISPER_DEVICE=cpu` |
| « YouTube a refusé la requête (vérification anti-robot) » | Réessayer plus tard. L'application ne contourne pas cette protection |
| Échec yt-dlp sur une vidéo publique | YouTube change souvent : mettre à jour yt-dlp (`pip install -U "yt-dlp[default]"`), puis relancer le job |
| « IA indisponible (clé API absente) » | Ajouter `ANTHROPIC_API_KEY` dans `.env` puis redémarrer ; sinon l'analyse se fait par signaux |
| « Plafond mensuel atteint » | Augmenter le plafond dans Paramètres ou attendre le mois suivant ; les extraits restants sont évalués par signaux |
| « Clé API refusée par Anthropic » | Clé invalide ou révoquée : la remplacer dans `.env` puis redémarrer, et relancer le job |
| « Crédit API Anthropic insuffisant » | Recharger le compte (console.anthropic.com, Plans & Billing), puis relancer le job |
| « Contrôle qualité échoué » | Le fichier produit est invalide (voir l'onglet Contrôle qualité du short) : relancer le montage ; si cela persiste, essayer l'encodeur libx264 dans le profil |
| Sous-titres sans les bonnes polices | Les polices proposées sont celles de Windows (`C:\Windows\Fonts`) |
| Transcription lente | Un jeu ou une autre application utilise le GPU ; voir `docs/BENCHMARK_ASR.md` (`GSA_WHISPER_BEAM_SIZE=1`) |
| « Détecteur de musique absent », « Détecteur de visages absent », « Aucune voix installée » | `cd backend; .\.venv\Scripts\python.exe -m app.cli.models download --all` |
| « Aucune musique utilisable » | Déposer des morceaux dans `GSA_DATA_DIR\music`, page Musique > Analyser le dossier, renseigner la licence et confirmer |
| Musique d'origine « encore détectable » | Augmenter l'atténuation dans le profil (jusqu'à 40 dB) et écouter l'aperçu audio du short |
| Narration jamais ajoutée | Normal si l'IA la juge inutile (parole dense) ; elle n'est jamais générée sans IA. Vérifier aussi que le profil est en mode « Si l'IA la juge utile » |

## Limites connues

- Atténuer la musique d'origine réduit le risque de réclamation sans le supprimer : le
  détecteur repère encore une musique très atténuée (mesuré sur un extrait réel : musique sur
  46 % des secondes, encore détectable sur 29 % à -15 dB et 17 % à -35 dB, 0 % sur les voix
  seules). Les bruitages du jeu sont dans les mêmes pistes que la musique : ils baissent aussi
  pendant les passages musicaux.
- Facecam : validé sur des images sans visage (aucun faux positif sur 20 images) et par des
  tests sur des détections simulées ; **pas encore validé sur une vraie vidéo avec facecam**.
  Un facecam sans visage visible (joueur hors champ) n'est pas détecté.
- Narration : voix de synthèse (Piper), intelligible mais reconnaissable comme telle
  (re-transcription Whisper : 72 % des mots en français, 86 % en anglais) ; sans surlignage
  mot à mot. Elle n'est proposée que si l'IA la juge utile, ce qui est rare sur une vidéo
  très commentée.
- Les sous-titres traduits sont répartis sur la durée des phrases d'origine (pas de
  surlignage mot à mot en traduction).
- Aucune publication automatique : les shorts exportés sont à publier vous-même.
- L'énergie sonore signale un son plus fort que d'habitude, pas sa nature : la détection
  d'extraits ne reconnaît ni rires ni cris (la musique n'est détectée qu'au montage).
- Le mode « signaux seuls » ne comprend pas le contenu : ses notes sont approximatives
  (originalité fixée à 5) et clairement signalées comme telles.
- Le coût affiché est calculé à partir des jetons facturés et des tarifs configurés : à
  rapprocher de la facture Anthropic, qui fait foi.
- Sources : YouTube uniquement (une vidéo par lien, pas de playlist).
- Transcription mesurée sur une vraie vidéo de 10 min (33× temps réel, GPU libre) ; la précision
  sur des parties avec voix superposées, cris ou musique forte reste à évaluer.
- Le téléchargement privilégie le H.264 (`avc1`) : la build FFmpeg « essentials » ne décode
  l'AV1 que lentement (libaom) ou via le GPU. Les vidéos déjà importées en AV1 restent lisibles.
- faster-whisper 1.2.1 ne peut pas décoder lui-même l'audio avec PyAV 19 : l'application lui
  fournit directement le WAV extrait par FFmpeg (aucun impact fonctionnel).
- Paramètres en lecture seule dans l'interface (modification via `.env`).
- `stop.ps1` arrête les processus de force : un job en cours est repris au redémarrage suivant
  (après `GSA_WORKER_STALE_SECONDS`), sans rejouer les étapes terminées.
- `npm audit` signale des vulnérabilités modérées dans les outils de développement (ESLint /
  minimatch) ; elles ne sont pas embarquées dans l'application.
- Les jobs de démonstration de la Phase 1 restent disponibles (section « Outils de test » d'un
  projet) pour tester la file sans télécharger de vidéo.
