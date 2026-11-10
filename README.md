# Gaming Shorts AI

Application locale (Windows 11) destinée à transformer des vidéos longues de gameplay en shorts verticaux.

> **État actuel : Phase 1 — fondations.** L'application gère une bibliothèque de projets et une
> file d'attente persistante, avec **uniquement des jobs de démonstration**. Le téléchargement
> (yt-dlp), l'analyse IA, la détection de clips et le montage vidéo **ne sont pas encore
> implémentés**.

Documents de référence (racine du dépôt) : `CAHIER_DES_CHARGES.md`, `ARCHITECTURE_TECHNIQUE.md`,
`CLAUDE_INSTRUCTIONS.md`, `PROMPT_INITIAL_CLAUDE_CODE.txt`. Audit machine : `docs/ENVIRONNEMENT.md`.

## Architecture (Phase 1)

```text
Navigateur ──► Frontend React/TS (Vite, 127.0.0.1:5173)
                   │  /api (proxy Vite)
                   ▼
              API FastAPI (127.0.0.1:8000) ──► SQLite (GSA_DATA_DIR\gaming_shorts.db, WAL)
                                                   ▲
              Worker (processus séparé) ───────────┘  réclame les jobs un par un
```

- **Backend** (`backend/app`) : `core/` (config, logs JSON, erreurs), `models/` (Project, Job,
  JobStep, WorkerHeartbeat), `db/` (moteur, migrations), `services/` (projets, file d'attente,
  catalogue des types de jobs), `api/` (routes), `workers/` (boucle du worker, handlers de démo).
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

Documentation interactive : http://127.0.0.1:8000/docs (quand l'API tourne).

## Prérequis

| Outil | Version validée | Installation |
|---|---|---|
| Windows 11 | 10.0.26200 | — |
| Python | 3.13.15 (≥ 3.12 requis) | https://www.python.org/downloads/windows/ (cocher « Add to PATH ») |
| Node.js / npm | 24.18.0 / 11.16.0 | https://nodejs.org (LTS) |
| FFmpeg / ffprobe | 8.1.1 | `winget install Gyan.FFmpeg.Essentials` — détecté mais **pas encore utilisé** |

Aucune clé API, aucun modèle IA et aucun Docker ne sont nécessaires en Phase 1.

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
.\.venv\Scripts\python.exe -m pytest           # tests unitaires, API, file, reprise après crash
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

## Données et confidentialité

- Tout est stocké localement dans `GSA_DATA_DIR` ; rien n'est envoyé sur Internet.
- `data/`, bases SQLite, médias, modèles, `.env` et `.run/` sont exclus de Git (`.gitignore`).
- Logs JSON structurés : `GSA_DATA_DIR\logs\api.log`, `worker.log`, `migrate.log` (rotation 5 Mo × 3).
- La suppression d'un projet demande une confirmation et efface ses jobs (en base). En Phase 1,
  aucun fichier n'est associé aux projets.

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

## Limites connues (Phase 1)

- Pas de téléchargement, d'analyse IA, de détection de clips, de montage ni d'export : uniquement
  des jobs de démonstration clairement signalés.
- Paramètres en lecture seule dans l'interface (modification via `.env`).
- `stop.ps1` arrête les processus de force : un job en cours est repris au redémarrage suivant
  (après `GSA_WORKER_STALE_SECONDS`), sans rejouer les étapes terminées.
- `npm audit` signale des vulnérabilités modérées dans les outils de développement (ESLint /
  minimatch) ; elles ne sont pas embarquées dans l'application.
