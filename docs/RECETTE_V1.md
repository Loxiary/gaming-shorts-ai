# Recette V1 — Gaming Shorts AI

Vérification des 17 critères d'acceptation du cahier des charges (§18) et des questions
techniques ouvertes (§19), le **11/11/2026**, version 0.6.0, sur la machine de référence
(Windows 11, RTX 3060 Ti 8 Go, 16 Go de RAM, données sur `D:`).

Sources des preuves :
- **Tests automatisés** : 147 tests backend (pytest, FFmpeg réel, IA et modèles simulés) et
  41 tests frontend (Vitest). Tous passent.
- **Essais réels** : une vidéo YouTube réelle (Satisfactory, 10 min 33 s, 1080p60, commentaire
  en anglais), importée, transcrite, analysée avec Claude Sonnet 5.5 (vision) et montée.
- Légende : ✅ satisfait · ⚠️ satisfait avec réserve · ❌ non satisfait.

## Critères d'acceptation

| # | Critère | État | Preuve |
|---|---|---|---|
| 1 | Plusieurs liens peuvent être ajoutés à la file | ✅ | Import de 1 à 20 liens (doublons, liens refusés signalés un par un) ; `test_ingest_pipeline` |
| 2 | Une vidéo accessible et autorisée peut être téléchargée et prétraitée | ✅ | Essai réel : téléchargement, analyse technique, audio 16 kHz et transcription en 57 s |
| 3 | Les tâches survivent à un redémarrage | ✅ | Étapes persistées, reprise des jobs abandonnés ≤ 30 s, étapes réussies jamais rejouées (`test_queue`). Phase 6 : pause et reprise sûres entre deux étapes |
| 4 | La transcription et ses horodatages sont conservés | ✅ | Segments et mots horodatés en base ; consultables dans le projet ; transcription source jamais modifiée (une traduction est stockée à part) |
| 5 | L'analyse détecte des candidats avec explications | ✅ | Essai réel : 11 extraits proposés, résumé, raison, moments clés et avertissements par extrait |
| 6 | Chaque candidat reçoit un score et ses critères | ✅ | 7 critères notés et justifiés, note globale pondérée par profil |
| 7 | Le seuil est configurable | ✅ | Par profil, et réglable après coup sans nouvel appel à l'IA (« Appliquer le seuil ») |
| 8 | Les clips générés respectent 61 à 180 s | ✅ | Fenêtres limitées à 61–180 s dès la détection ; contrôle qualité **critique** sur le fichier produit ; essais réels : 68 et 78 s |
| 9 | Exports 9:16, 1080 × 1920, MP4 H.264/AAC | ✅ | Contrôle qualité critique (résolution, codecs, yuv420p, lecture complète) ; vérifié par ffprobe sur les rendus réels |
| 10 | Fond flouté et recadrage facecam fonctionnent ou signalent leurs limites | ⚠️ | Fond flouté : ✅ sur rendus réels. Facecam : détection et recadrage testés sur détections simulées, **aucun faux positif sur 30 images réelles sans facecam** ; cas douteux et pertes > 35 % signalés. **Pas encore validé sur une vraie vidéo avec facecam** |
| 11 | Les sous-titres sont synchronisés | ✅ | Mots horodatés par Whisper, mot prononcé surligné ; vérifié visuellement sur rendu réel |
| 12 | La narration, si utilisée, est mixée avec ducking | ⚠️ | Ducking du jeu (-9 dB) et de la musique (-8 dB) calé sur les horodatages ; vérifié par test de bout en bout (niveaux mesurés). Sur la vidéo réelle, l'IA a jugé la narration inutile (commentaire déjà dense) : **narration non encore entendue sur un rendu réel**. La voix Piper seule est validée (re-transcrite à 72 % en français, 86 % en anglais) |
| 13 | Le rapport de risques est consultable | ✅ | Par short : source, droits, musique d'origine, facecam, transformation, contenu réutilisé, crédits, recommandations ; joint à la fiche d'export |
| 14 | L'utilisateur peut confirmer un export malgré les avertissements | ✅ | Case de confirmation obligatoire, aucun verrou fondé sur les risques ; seul un fichier techniquement invalide ne s'exporte pas |
| 15 | Coûts API suivis, API désactivables | ✅ | Chaque appel enregistré (jetons, coût, statut), plafond mensuel vérifié **avant** chaque appel, interrupteur dans Paramètres, mode « signaux seuls » sans IA |
| 16 | Fichiers et paramètres conservés dans la bibliothèque | ✅ | Projets, sources, transcriptions, analyses, rendus, rapports, exports et coûts en base locale. Phase 6 : sauvegarde ZIP de la base et des paramètres (sans secret), restauration hors ligne, export et import des profils |
| 17 | Un contrôle qualité vérifie les fichiers réellement produits | ✅ | ffprobe et décodage complet du MP4 produit, mesure EBU R128 (-14,4 LUFS mesuré sur rendu réel) |

**Bilan : 15 critères satisfaits, 2 avec réserve (10 et 12), aucun non satisfait.** Les deux
réserves tiennent au manque de matériel de test réel (vidéo avec facecam, extrait où l'IA
juge une narration utile), pas à une fonction absente.

## Questions techniques ouvertes (§19)

| Question | Réponse mesurée |
|---|---|
| VRAM réelle du GPU | 8 Go (RTX 3060 Ti), dont ≈ 4,4 Go libres avec les applications de bureau ouvertes (`docs/ENVIRONNEMENT.md`) |
| Modèles locaux adaptés à 16 Go de RAM et à la VRAM | Whisper large-v3-turbo int8_float16 sur GPU : 33,6 × temps réel. Audio (PANNs, Demucs) et voix (Piper) sur le processeur, sans concurrence avec le GPU. Facecam : YuNet (0,3 Mo) |
| Qualité de détection des événements gaming | Correcte sur la vidéo testée (extraits calés sur des phrases complètes ; 1 fausse alerte de coupure sur 11). **Une seule vidéo réelle évaluée** : à confirmer sur d'autres jeux et styles (action, sans commentaire) |
| Facecam par recadrage selon les layouts | Recadrage du côté qui retire le moins d'image, fond flouté et plein cadre. Non validé sur une vraie incrustation (voir critère 10) |
| Performances de séparation audio | Demucs htdemucs sur processeur : ≈ 0,5 × temps réel (32 s pour 68 s d'audio) ; montage complet d'un short de 68 s : 113 s |
| Coûts API réels par heure de vidéo | Analyse avec vision : **0,26 $ pour 11 extraits** (≈ 0,024 $ par extrait, 8 images chacun) sur une vidéo de 10 min 33 s. Le nombre d'extraits évalués est plafonné par profil (12 par défaut) : **≈ 0,26 à 0,30 $ par analyse, quelle que soit la durée au-delà d'environ 12 minutes**, soit au plus ≈ 0,30 $ par heure de vidéo avec les réglages par défaut. Montage : 0,013 à 0,021 $ par short (plan éditorial, plus la traduction éventuelle). Dépense totale de la recette : 0,83 $ |
| Licences des modèles, dépendances, voix, musiques et effets | Tableau des modèles dans le README (MIT, CC BY 4.0 avec crédit automatique, CC0). Voix à licence non commerciale ou incertaine écartées. Musique : uniquement des fichiers de l'utilisateur avec licence saisie et autorisation confirmée. Aucun effet sonore fourni. Piper : moteur GPL exécuté en local sans modification |

## Écarts connus et suites possibles

- **Facecam et narration** : valider sur une vidéo avec webcam incrustée et sur un extrait sans
  commentaire (où une narration est utile).
- **Une seule source réelle testée** : la sélection des extraits et les seuils par défaut
  gagneraient à être réglés sur plusieurs jeux.
- **Transitions et effets ponctuels** (§8) : non réalisés en V1 (zooms seulement), choix de
  périmètre de la Phase 6.
- **Musique d'origine** : une atténuation réduit le risque de réclamation sans le supprimer ; le
  détecteur repère encore une musique très atténuée (voir README, « Limites connues »).
- **Concurrence** : un seul job à la fois (choix du cahier des charges, §15).
- **Restauration** : en ligne de commande uniquement, application arrêtée (choix de sûreté).
- **Hors V1 (§17)** : éditeur de timeline, publication directe, planification, statistiques.
