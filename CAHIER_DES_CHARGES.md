# Gaming Shorts AI — Cahier des charges fonctionnel

**Version :** 1.0 — 10 novembre 2026  
**Statut :** périmètre initial validé, détails techniques à confirmer par prototype.

## 1. Objectif

Développer une application locale sous Windows 11 qui transforme des vidéos longues de gameplay en plusieurs vidéos verticales prêtes à être vérifiées puis publiées manuellement sur TikTok et YouTube Shorts.

Le cas d'usage initial vise des vidéos de gameplay, principalement GTA 6, provenant de liens YouTube. L'architecture doit rester extensible à d'autres jeux et sources légalement accessibles.

L'application doit automatiser autant que possible le téléchargement autorisé, l'analyse, la sélection éditoriale, le montage, le mixage audio, les contrôles qualité et l'export.

## 2. Principes non négociables

1. **L'utilisateur garde toujours la décision finale.** L'IA formule des recommandations et avertissements, mais ne bloque jamais volontairement l'export en raison d'un score de risque, d'un droit incertain ou d'une recommandation éditoriale.
2. Une confirmation humaine explicite est demandée avant chaque export final. L'utilisateur peut confirmer l'export malgré les avertissements.
3. Les résultats IA sont des estimations, pas des garanties de viralité, de conformité juridique ou d'éligibilité à la monétisation.
4. Les traitements locaux sont privilégiés. Les API payantes sont utilisées uniquement lorsque cela apporte une valeur claire et avec contrôle des coûts.
5. Les tâches doivent être traçables, reprenables après interruption et testables indépendamment.
6. Les transcriptions originales restent fidèles. Une traduction ou adaptation est stockée séparément et ne remplace jamais la transcription source.

## 3. Utilisateur et environnement

- Système : Windows 11.
- CPU : AMD Ryzen 5 3600.
- RAM : 16 Go DDR4.
- GPU déclaré : NVIDIA RTX 3060 Ti, mémoire indiquée par l'utilisateur comme 6 Go — **à vérifier** avec `nvidia-smi` avant de choisir les modèles.
- Stockage de travail : SSD avec environ 500 Go libres.
- Budget API cible : 30 à 50 € par mois, avec plafond configurable.
- Interface : application web locale préférée ; CLI acceptable pour diagnostic et administration.
- Langue de l'interface : français au départ, anglais acceptable si nécessaire.

## 4. Sources et importation

### V1
- Importer un ou plusieurs liens YouTube.
- Ajouter les tâches à une file d'attente.
- Afficher statut, progression, étapes, erreurs et durée.
- Mettre en pause/annuler si techniquement sûr.
- Relancer une tâche échouée à partir de la dernière étape valide.
- Conserver les métadonnées de source et l'URL d'origine.
- Utiliser `yt-dlp` uniquement dans le respect des lois, des droits applicables et des conditions de la plateforme. Ne pas contourner DRM, restrictions d'accès ou protections techniques.

### Hors périmètre initial
- Intégrations natives TikTok/Instagram/Twitch.
- Publication automatique.
- Téléchargement de sources protégées ou contournement d'accès.

## 5. Résultat vidéo attendu

- Format vertical 9:16.
- Résolution cible : 1080 × 1920.
- Conteneur MP4.
- Codec vidéo cible : H.264.
- Audio AAC.
- Durée impérative : **minimum 61 secondes et maximum 180 secondes**.
- Chaque export doit être contrôlé techniquement avant d'être proposé à la validation.
- Le nombre de clips est déterminé par l'analyse IA et le seuil de sélection configurable.
- Si aucun extrait pertinent ne respecte la durée minimale, le logiciel doit l'indiquer clairement et ne pas fabriquer artificiellement un clip incohérent.

## 6. Analyse du contenu

L'analyse doit combiner, autant que possible :
- transcription et horodatage des paroles ;
- analyse audio (cris, rires, réactions, événements sonores) ;
- analyse visuelle de séquences, pas seulement d'images isolées ;
- détection de changements de scènes ;
- compréhension du contexte et des événements de gameplay ;
- identification de moments surprenants, drôles, impressionnants, tendus ou narrativement autonomes.

L'analyse visuelle doit utiliser des échantillons d'images/vidéo horodatés et adapter la fréquence d'échantillonnage à l'activité. Ne pas supposer qu'une image isolée suffit à comprendre un événement.

## 7. Détection et sélection des clips

Chaque candidat doit avoir :
- timestamp de début et de fin ;
- durée ;
- résumé factuel ;
- raison de sélection ;
- transcription associée ;
- note globale de potentiel viral ;
- notes par critère ;
- niveau de confiance/incertitude ;
- éventuels avertissements.

Critères configurables proposés :
- force de l'accroche ;
- divertissement / intensité ;
- compréhension autonome ;
- progression narrative ;
- potentiel de rétention ;
- originalité / valeur ajoutée éditoriale ;
- qualité audio-visuelle.

Le score doit être explicable. Il ne doit pas être présenté comme une prédiction certaine des vues.

Comportement :
- générer tous les candidats dépassant le seuil choisi ;
- seuil configurable globalement et par profil ;
- éviter les doublons et les chevauchements excessifs ;
- privilégier des extraits ayant un début, un développement et une fin compréhensibles ;
- respecter strictement 61 à 180 secondes ;
- laisser l'utilisateur modifier les seuils et paramètres.

## 8. Style de montage gaming

Style initial : montage gaming dynamique, adapté à TikTok et YouTube Shorts.

- Gameplay en premier plan.
- Fond agrandi et flouté derrière le gameplay lorsque nécessaire.
- Sous-titres animés, synchronisés, mot par mot ou par groupes de mots selon lisibilité.
- Mots importants mis en couleur.
- Zooms automatiques sur les moments pertinents.
- Transitions et effets ponctuels, sans surcharge systématique.
- Accroche au début.
- Appel à l'action en conclusion.
- Profils de montage enregistrables et sélectionnables.

### Facecam
- Détecter si possible les zones facecam/webcam.
- Le choix initial demandé est de recadrer pour exclure complètement le facecam.
- Ne pas remplacer automatiquement par un floutage.
- Si le recadrage enlève trop de gameplay, masque un élément important ou ne peut pas exclure proprement le visage, signaler le problème dans le rapport qualité. Ne pas prétendre avoir supprimé le facecam si ce n'est pas vérifié.
- Ne pas utiliser de reconnaissance d'identité : seule la détection de région/personne est pertinente.

## 9. Audio et narration

### Audio source
- Préserver les bruitages du jeu.
- Conserver les voix originales utiles, sauf paramètre contraire.
- Détecter et atténuer/supprimer les musiques originales susceptibles de poser des problèmes de droits, dans la limite des capacités techniques.
- Une séparation audio parfaite ne doit jamais être promise : si musique et bruitages sont mélangés, le résultat peut être imparfait.
- Permettre de régler les niveaux et de préécouter le mixage.

### Musique ajoutée
- Ajouter une musique adaptée à l'ambiance uniquement depuis une source autorisée pour l'usage envisagé.
- Stocker la provenance/licence ou les informations d'autorisation disponibles.
- Ne pas utiliser automatiquement une musique commerciale ou simplement populaire.

### Narration
- L'IA décide si une narration apporte une valeur réelle.
- Narration originale, factuelle, contextualisante et concise.
- Ne pas inventer d'événements, de dialogues ou d'intentions du créateur.
- Plusieurs voix sélectionnables.
- Langue de sortie sélectionnable indépendamment de la langue source.
- La narration doit être mixée avec ducking : réduction du volume du gameplay pendant la voix.
- Prévoir un réglage permettant de désactiver narration, musique ou effets.

## 10. Sous-titres et langues

- Transcription source fidèle mot pour mot, avec timestamps.
- Correction technique de ponctuation/capitalisation possible sans réécrire le contenu.
- Traduction séparée si la langue de sortie diffère.
- Choix de la langue de sortie.
- Sous-titres animés avec mise en évidence de mots importants.
- Les sous-titres traduits doivent être identifiés comme traduction et ne pas être présentés comme transcription verbatim de la langue source.

## 11. Accroches et appels à l'action

- Mélange de phrases marquantes réellement prononcées et d'accroches originales générées.
- L'accroche générée ne doit pas tromper ni promettre un événement absent.
- Appel à l'action configurable, par exemple question à la communauté ou invitation à suivre le compte.
- Possibilité de désactiver ou personnaliser les CTA par profil.

## 12. Profils de montage

V1 doit permettre de créer, modifier, dupliquer, sélectionner et supprimer des profils.

Exemples initiaux :
- GTA 6 — Viral.
- GTA 6 — Humour.
- GTA 6 — Action.
- Gaming — Immersion.
- Gaming — Histoire.

Paramètres possibles :
- seuil de score ;
- critères de scoring et pondérations ;
- langue de sortie ;
- voix et vitesse de narration ;
- présence de narration ;
- style, police, taille et couleurs des sous-titres ;
- intensité des zooms et effets ;
- musique et niveau sonore ;
- CTA ;
- paramètres de rendu.

## 13. Contrôle des risques et validation humaine

Pour chaque clip, afficher un rapport informatif :
- source et créateur si les informations sont disponibles ;
- droits/autorisation : confirmé par l'utilisateur, inconnu ou autre état documenté ;
- musique détectée ou risque audio potentiel ;
- niveau de transformation éditoriale estimé ;
- risques de contenu réutilisé ;
- avertissements et limites de l'analyse ;
- recommandations.

Ne pas affirmer qu'un clip est juridiquement autorisé ou garanti monétisable sur la seule base d'une analyse automatique.

**Règle absolue : aucun verrou automatique d'export fondé sur ces risques.** Après lecture du rapport, l'utilisateur confirme explicitement ou annule l'export. La confirmation permet d'exporter même en présence d'avertissements.

Le logiciel doit respecter les droits d'auteur, les conditions des plateformes et les lois applicables. La possibilité technique d'importer une vidéo ne constitue pas une autorisation de la réutiliser.

## 14. Bibliothèque et stockage

V1 doit fournir une bibliothèque locale avec :
- projets et sources ;
- métadonnées et URL ;
- état des tâches ;
- transcription ;
- candidats et scores ;
- profils utilisés ;
- rapports de risques ;
- fichiers exportés ;
- historique des traitements et coûts API.

Prévoir :
- gestion de l'espace disque ;
- rétention configurable des sources et fichiers temporaires ;
- suppression de projet avec confirmation ;
- absence d'envoi cloud des fichiers sans consentement explicite ;
- sauvegarde/export de la base et des paramètres.

## 15. File d'attente et robustesse

- Une file d'attente multi-liens.
- Traitement séquentiel par défaut pour respecter les limites CPU/RAM/VRAM.
- Concurrence configurable ultérieurement.
- Étapes persistées en base.
- Reprise après crash sans refaire les étapes réussies.
- Gestion des erreurs réseau, API, disque et GPU.
- Journalisation structurée.
- Annulation sûre entre les étapes.
- Protection contre les doublons de tâches.

## 16. Interface V1

Application web locale :
- tableau de bord ;
- formulaire d'importation multi-liens ;
- file d'attente et progression ;
- détail d'un projet ;
- liste des clips candidats et scores ;
- réglages globaux ;
- gestion des profils ;
- bibliothèque ;
- rapport de risques ;
- confirmation d'export ;
- historique des coûts API.

L'éditeur de timeline et les corrections manuelles avancées sont reportés en V2. La V1 doit toutefois permettre de prévisualiser les clips et de valider leur export.

## 17. V2 — Hors périmètre V1

- éditeur vidéo intégré avec timeline ;
- édition manuelle avancée ;
- publication directe ;
- gestion multi-comptes sociaux ;
- planification des publications ;
- récupération des statistiques de performance.

## 18. Critères d'acceptation V1

La V1 est acceptable lorsque :
1. Plusieurs liens peuvent être ajoutés à la file.
2. Une vidéo accessible et autorisée peut être téléchargée/prétraitée.
3. Les tâches survivent à un redémarrage.
4. La transcription et ses timestamps sont conservés.
5. L'analyse détecte des candidats avec explications.
6. Chaque candidat reçoit un score et ses critères.
7. Le seuil est configurable.
8. Les clips générés respectent 61 à 180 secondes.
9. Les exports sont en 9:16, 1080 × 1920 cible, MP4 H.264/AAC.
10. Le fond flouté et le recadrage facecam fonctionnent ou signalent leurs limites.
11. Les sous-titres sont synchronisés.
12. La narration, si utilisée, est mixée avec ducking.
13. Le rapport de risques est consultable.
14. L'utilisateur peut confirmer un export malgré les avertissements.
15. Les coûts API sont suivis et les API peuvent être désactivées.
16. Les fichiers et paramètres sont conservés dans la bibliothèque.
17. Un contrôle qualité vérifie les fichiers réellement produits.

## 19. Questions techniques ouvertes

Claude doit documenter et tester, sans inventer de certitude :
- la VRAM réelle du GPU ;
- les modèles locaux adaptés à 16 Go RAM et à la VRAM disponible ;
- la qualité de détection des événements gaming ;
- la faisabilité du facecam par recadrage selon les layouts ;
- les performances de séparation audio ;
- les coûts API réels par heure de vidéo ;
- les licences des modèles, dépendances, voix, musiques et effets sonores.
