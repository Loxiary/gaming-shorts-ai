# Gaming Shorts AI — Architecture technique

**Version :** 1.0 — proposition à valider par prototypes  
**Principe :** architecture locale, modulaire, hybride et reprenable.

## 1. Décision d'architecture

Construire une application web locale avec :
- frontend React + TypeScript ;
- backend Python + FastAPI ;
- base SQLite ;
- traitement média via FFmpeg ;
- orchestration par étapes persistées ;
- adaptateurs interchangeables pour modèles locaux et API.

Ne pas surconcevoir : livrer une tranche verticale fonctionnelle avant de multiplier les composants.

## 2. Schéma logique

```text
Navigateur local
      |
React + TypeScript
      |
FastAPI (localhost)
      |
Application services / orchestration
      |
      +---- Queue & task state (SQLite)
      |
      +---- Downloader adapter (yt-dlp)
      |
      +---- Media preprocessing (FFmpeg / ffprobe)
      |
      +---- Transcription adapter (Faster-Whisper ou autre)
      |
      +---- Scene & visual analysis
      |
      +---- LLM adapter (local / API)
      |
      +---- Clip selection & scoring
      |
      +---- Narration / TTS adapter
      |
      +---- Audio processing
      |
      +---- Rendering & QC
      |
      +---- Local storage / library
```

## 3. Stack proposée

Les versions doivent être choisies et verrouillées après vérification de compatibilité Windows/Python/CUDA. Ne pas fixer des versions au hasard.

### Frontend
- React
- TypeScript
- Vite
- bibliothèque de composants légère
- client API typé
- WebSocket ou Server-Sent Events pour progression en direct

### Backend
- Python
- FastAPI
- Pydantic pour validation des schémas
- SQLAlchemy ou SQLModel avec SQLite
- migrations Alembic
- processus worker séparé du serveur web

### Média
- FFmpeg et ffprobe pour extraction, rendu, encodage et contrôle
- OpenCV pour traitement d'image si nécessaire
- PySceneDetect pour proposer des changements de scène
- yt-dlp pour sources accessibles et autorisées

### IA
- Faster-Whisper ou alternative validée pour ASR local
- modèle vision/vidéo à sélectionner après benchmark
- LLM local quantifié via un runtime adapté ou API externe
- adaptateur TTS local/API
- modèle de séparation audio à sélectionner après test qualité/VRAM

Les noms ci-dessus sont des candidats, pas une obligation. Chaque composant doit avoir une interface abstraite afin de pouvoir le remplacer.

## 4. Contraintes matérielles

Machine cible :
- Windows 11
- Ryzen 5 3600
- 16 Go RAM DDR4
- RTX 3060 Ti déclarée par l'utilisateur, VRAM à vérifier (l'utilisateur indique 6 Go ; ne pas présumer la capacité exacte)
- SSD avec environ 500 Go libres

Avant toute sélection de modèles :
1. exécuter `nvidia-smi` ;
2. relever modèle GPU, VRAM totale et VRAM disponible ;
3. relever version du pilote et CUDA supportée ;
4. mesurer RAM libre ;
5. tester un petit modèle ASR et un petit modèle vision/LLM séparément ;
6. documenter vitesse, mémoire maximale et qualité.

Ne pas lancer plusieurs modèles lourds simultanément par défaut. Traiter les vidéos de manière séquentielle. Décharger les modèles et libérer la mémoire entre les étapes si nécessaire.

## 5. Organisation du dépôt

```text
gaming-shorts-ai/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── queue/
│   │   │   ├── projects/
│   │   │   ├── profiles/
│   │   │   ├── exports/
│   │   │   └── settings/
│   │   └── services/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── workers/
│   │   ├── adapters/
│   │   │   ├── downloader/
│   │   │   ├── asr/
│   │   │   ├── llm/
│   │   │   ├── vision/
│   │   │   ├── tts/
│   │   │   └── audio/
│   │   └── main.py
│   └── tests/
├── data/                 # local runtime data, ignored by git
├── config/
├── scripts/
├── docs/
├── .env.example
├── .gitignore
└── README.md
```

Ne pas versionner les vidéos, exports, bases de données locales, secrets ou clés API.

## 6. Pipeline de traitement

Chaque étape doit avoir une entrée, une sortie, un statut, des logs et une version de configuration.

Étapes proposées :
1. `queued`
2. `validating_source`
3. `downloading`
4. `probing_media`
5. `extracting_audio`
6. `transcribing`
7. `detecting_scenes`
8. `analyzing_content`
9. `generating_candidates`
10. `scoring_candidates`
11. `selecting_clips`
12. `creating_editorial_plan`
13. `generating_narration`
14. `processing_audio`
15. `rendering`
16. `quality_check`
17. `awaiting_user_export_confirmation`
18. `exported` ou `cancelled` / `failed`

Le pipeline doit être idempotent autant que possible. Une reprise ne doit pas refaire les étapes valides si leurs entrées et versions n'ont pas changé.

## 7. Modèle de données initial

Tables proposées :
- `projects`
- `source_media`
- `jobs`
- `job_steps`
- `transcripts`
- `transcript_segments`
- `scene_segments`
- `clip_candidates`
- `clip_scores`
- `editorial_plans`
- `voice_profiles`
- `editing_profiles`
- `exports`
- `risk_reports`
- `api_usage`
- `app_settings`

Utiliser des identifiants stables, dates UTC ISO, chemins relatifs dans la racine de données, et contraintes d'intégrité.

## 8. Contrats internes

Définir des schémas Pydantic versionnés pour :
- transcription et segments ;
- scène ;
- candidat de clip ;
- score détaillé ;
- plan éditorial ;
- narration ;
- paramètres de rendu ;
- rapport de risques ;
- résultat QC.

Les réponses LLM doivent être structurées et validées. Si la sortie est invalide, prévoir une stratégie de réparation/retry limitée, puis une erreur explicite.

Le LLM ne doit jamais fournir directement des commandes shell arbitraires à exécuter. Les paramètres doivent être validés et transmis à des fonctions contrôlées.

## 9. Analyse multimodale et coût

Ne pas transmettre une vidéo entière à une API par défaut.

Approche :
1. extraire localement audio, transcription, scènes et images représentatives ;
2. repérer les fenêtres candidates ;
3. envoyer seulement les fenêtres utiles et les informations horodatées ;
4. réduire la taille/fréquence des images selon le modèle ;
5. mettre en cache les analyses avec identifiants de modèle et empreinte des entrées ;
6. compter tokens, requêtes, durée et coût estimé/réel ;
7. demander confirmation ou respecter un plafond avant dépense.

Prévoir un mode 100 % local lorsque possible et un mode API désactivable.

## 10. File d'attente

Pour la V1, une file persistante SQLite et un worker unique peuvent suffire. Ne pas introduire Redis/Celery sans besoin mesuré.

- Un seul traitement lourd à la fois par défaut.
- Statut et progression persistés.
- Verrouillage pour éviter deux workers sur la même tâche.
- Reprise après redémarrage.
- Annulation à des points sûrs.
- Gestion des timeouts et retries limités.
- État d'erreur compréhensible par l'utilisateur.

## 11. API locale

Exemples de routes à définir :
- `POST /api/projects` : créer projet/importer source
- `GET /api/projects`
- `GET /api/projects/{id}`
- `POST /api/jobs`
- `GET /api/jobs`
- `POST /api/jobs/{id}/cancel`
- `POST /api/jobs/{id}/retry`
- `GET /api/jobs/{id}/events`
- `GET /api/profiles`
- `POST /api/profiles`
- `PUT /api/profiles/{id}`
- `GET /api/clips/{id}`
- `GET /api/clips/{id}/risk-report`
- `POST /api/clips/{id}/confirm-export`
- `GET /api/exports`

Les routes définitives doivent suivre les besoins UI et les schémas documentés.

## 12. Sécurité locale

- Lier le serveur à `127.0.0.1` par défaut, pas à toutes les interfaces réseau.
- Ne pas exposer l'application sur le réseau sans demande explicite.
- Protéger les secrets dans `.env` ou stockage sécurisé approprié.
- Ne jamais logger les clés API.
- Valider URL, chemins, extensions et tailles.
- Éviter les traversées de chemins.
- Ne pas exécuter de commandes construites à partir d'entrées non fiables.
- Vérifier les fichiers avant lecture et après rendu.
- Respecter droits d'auteur, conditions des sites et restrictions techniques ; aucun contournement DRM ou paywall.

## 13. Stockage et rétention

Prévoir des dossiers configurables :
- `data/sources`
- `data/temp`
- `data/projects`
- `data/exports`
- `data/models`
- `data/logs`

Les fichiers volumineux doivent pouvoir être supprimés sans casser les métadonnées de bibliothèque. Afficher l'espace utilisé et les options de nettoyage. Ne supprimer aucune source/export sans règle claire et confirmation utilisateur.

## 14. Contrôle qualité vidéo

Après rendu, vérifier avec ffprobe et/ou analyse :
- existence et taille du fichier ;
- durée comprise entre 61 et 180 secondes ;
- résolution et ratio ;
- codec vidéo/audio ;
- présence de pistes audio ;
- absence de fichier tronqué ;
- synchronisation audio/vidéo ;
- sous-titres incrustés ou piste prévue ;
- niveau audio et clipping ;
- présence éventuelle de facecam si détectable.

Le QC peut émettre des avertissements. Les contrôles techniques critiques doivent empêcher de marquer un fichier invalide comme prêt, mais l'utilisateur doit pouvoir examiner les diagnostics et choisir de poursuivre lorsque cela a du sens. Ne pas confondre ce contrôle technique avec le rapport juridique : ce dernier ne bloque jamais l'export.

## 15. Tests et observabilité

- Tests unitaires pour chaque service.
- Tests d'intégration avec courtes vidéos de test autorisées.
- Fixtures synthétiques pour ne pas dépendre d'un téléchargement YouTube à chaque test.
- Tests de reprise de tâche.
- Tests de coût/API mockés.
- Logs structurés avec project_id/job_id/step.
- Mesure CPU, RAM, VRAM et temps par étape.
- Rapport de benchmark reproductible.

## 16. Déploiement local

Prévoir scripts Windows :
- installation des dépendances ;
- vérification FFmpeg/ffprobe et GPU ;
- configuration `.env` ;
- démarrage backend + worker + frontend ;
- arrêt propre ;
- diagnostic.

Le démarrage doit être documenté et simple. Éviter Docker au départ si cela complique l'accès GPU ou FFmpeg sous Windows ; décider après un prototype.

## 17. Décisions à ne pas figer sans test

Claude doit comparer et documenter :
- SQLite + worker simple versus autre queue ;
- Faster-Whisper et modèle/taille adaptés ;
- vision locale vs API multimodale ;
- LLM local pour scoring vs API ;
- TTS local vs fournisseur externe ;
- séparation audio et qualité obtenue ;
- stratégie de facecam/cadrage ;
- coût moyen par heure de source.

Toute recommandation doit inclure : qualité, coût, latence, consommation RAM/VRAM, licence et complexité d'intégration.
