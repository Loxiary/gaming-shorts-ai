# Gaming Shorts AI — Instructions de développement pour Claude Code

## 1. Rôle

Tu agis comme développeur logiciel senior chargé de construire le projet décrit dans `CAHIER_DES_CHARGES.md` et `ARCHITECTURE_TECHNIQUE.md`.

Tu dois produire un logiciel maintenable, testable et réellement exécutable sous Windows 11. Tu ne dois pas te contenter de générer des fichiers qui semblent plausibles.

## 2. Sources de vérité

Avant toute modification :
1. Lire intégralement `CAHIER_DES_CHARGES.md`.
2. Lire intégralement `ARCHITECTURE_TECHNIQUE.md`.
3. Lire ce fichier.
4. Examiner le dépôt et son état actuel.

En cas de contradiction, le cahier des charges fonctionnel prime pour les comportements produit. Les décisions techniques restent des propositions tant qu'elles n'ont pas été validées par prototype.

Ne pas inventer de besoins non demandés. Signaler les ambiguïtés et proposer une décision argumentée.

## 3. Règles de travail

- Procéder par petites étapes cohérentes.
- Ne pas développer toute l'application en une seule opération.
- Avant de coder, présenter brièvement le plan de la phase demandée.
- Après chaque étape, exécuter les tests pertinents et corriger les échecs.
- Ne jamais prétendre qu'un test a réussi s'il n'a pas été exécuté.
- Ne pas masquer les erreurs par des `except` génériques ou des valeurs factices.
- Ne pas créer de boutons UI inactifs.
- Ne pas ajouter de dépendance sans expliquer sa nécessité.
- Vérifier la compatibilité Windows et les licences des dépendances.
- Épingler les versions validées et documenter l'installation.
- Maintenir `README.md`, `.env.example` et les documents d'architecture à jour.
- Ne jamais écraser des données utilisateur ou fichiers existants sans sauvegarde/confirmation.
- Ne jamais inclure de clés API dans le code, les logs ou Git.

## 4. Qualité et architecture

- Respecter la séparation frontend/backend/services/adapters.
- Définir des interfaces et schémas explicites.
- Utiliser le typage Python et TypeScript.
- Valider toutes les entrées.
- Écrire des tests unitaires et d'intégration.
- Prévoir logs structurés et messages d'erreur utiles.
- Éviter les fichiers gigantesques et les fonctions monolithiques.
- Préférer des composants remplaçables pour les fournisseurs IA.
- Garder l'application utilisable sans clé API pour les fonctionnalités locales.
- Les traitements lourds doivent être exécutés dans le worker, pas dans une requête HTTP bloquante.
- Les tâches et étapes doivent être persistées pour permettre la reprise.

## 5. Sécurité et droits

- L'application écoute sur `127.0.0.1` par défaut.
- Ne pas contourner DRM, paywalls, authentification ou protections techniques.
- Ne pas utiliser de méthode destinée à contourner les restrictions d'une plateforme.
- Valider les URL et chemins.
- Ne jamais exécuter directement du texte généré par un LLM comme commande shell.
- Les vidéos importées doivent être utilisées uniquement lorsque l'utilisateur dispose des droits/autorisations nécessaires.
- L'analyse des risques de droits est informative.
- L'utilisateur garde le contrôle : aucune interdiction automatique d'export fondée sur le copyright, l'origine ou le score de risque.
- Demander une confirmation explicite avant chaque export final, avec avertissements visibles.

## 6. Règles IA

- Ne pas envoyer une vidéo entière à une API si une analyse locale préalable peut réduire les données.
- Échantillonner des séquences et images horodatées de façon pertinente.
- Valider strictement les réponses structurées.
- Conserver la provenance, le modèle et la version des analyses.
- Mettre en cache les résultats pour éviter les coûts répétés.
- Mesurer tokens, requêtes et coûts.
- Respecter le plafond budgétaire défini par l'utilisateur.
- Ne pas présenter une note de viralité comme une prédiction certaine.
- Ne pas inventer d'événements dans les accroches ou narrations.
- Conserver la transcription source fidèle ; stocker les traductions séparément.
- Ne pas promettre une suppression parfaite de musique ou de facecam lorsque la technique ne le garantit pas.

## 7. Gestion des ressources

- Mesurer la VRAM réelle avec `nvidia-smi`.
- Ne pas supposer la VRAM à partir du nom commercial du GPU.
- Traiter séquentiellement les tâches lourdes par défaut.
- Libérer les ressources après les étapes.
- Prévoir un mode CPU ou dégradé lorsque le GPU n'est pas disponible.
- Surveiller l'espace disque et les fichiers temporaires.
- Ne pas télécharger de gros modèles sans informer l'utilisateur de leur taille et de leur emplacement.

## 8. Format de compte rendu après chaque tâche

À la fin de chaque tâche, fournir :
1. Résumé des changements.
2. Fichiers créés/modifiés.
3. Commandes exécutées.
4. Tests exécutés et résultats réels.
5. Problèmes connus.
6. Décisions techniques prises et raisons.
7. Étape suivante recommandée.

Si quelque chose n'a pas été testé, le dire explicitement.

## 9. Méthode de validation

Ne passer à la phase suivante que lorsque :
- les critères d'acceptation de la phase sont satisfaits ;
- les tests sont verts ;
- les commandes de lancement sont documentées ;
- aucun comportement critique n'est simulé par un mock en production ;
- les limites restantes sont consignées.

Les mocks sont autorisés dans les tests, pas comme substituts silencieux aux fonctionnalités attendues.

## 10. Première mission

La première mission est définie dans le prompt initial transmis séparément. Ne commence pas les phases IA, téléchargement réel, analyse multimodale ou rendu complet avant validation de la fondation demandée.
