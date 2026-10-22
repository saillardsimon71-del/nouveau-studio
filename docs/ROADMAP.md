# Roadmap — ordonnée par impact observé

Règle de priorité, rappelée par la mission : **qualité > fiabilité > coût >
intervention humaine > interface > fonctionnalités**. Ce document ne liste donc
pas des idées, mais les prochains gains mesurables.

## Bloc 1 — Lever les blocages de qualité (aucun développement produit)

Rien d'autre ne compte avant ces trois points : tant qu'aucune vidéo réelle n'a
été produite, tout le reste est de la spéculation.

1. **Louer 1× H100 80 Go pour une session de 3 h** (~9 $) et exécuter le test B
   (plan cinématographique) en `distilled` puis en `DFR`.
   *Sortie attendue* : deux MP4, les premiers chiffres réels de secondes GPU et
   le premier jugement de photoréalisme.
2. **Installer LongCat 1.5 + Chatterbox sur la même session** et exécuter le
   test A avec un vrai présentateur (image de référence + 10 s de voix réelle).
   *Sortie attendue* : premier lip-sync français, évaluation d'identité.
3. **Exécuter le test C** avec la référence retenue.
   *Sortie attendue* : décision « le personnage est récurrent ou il ne l'est pas ».

Livrable de fin de bloc : `benchmarks/results/` alimenté de résultats réels, et
la décision Go/No‑Go sur LTX‑2.5 et LongCat → DFR/720p. Budget : **< 30 $**.

## Bloc 2 — Corriger ce que les premiers rendus révèlent

Les actions ici dépendent des résultat du bloc 1 ; les candidats probables, par
ordre de fréquence observée dans ce type de pipeline :

4. **Stabilité de l'identité entre plans** : si l'image de référence seule ne
   suffit pas, ajouter l'encodage de la voix comme ancre, ou un LoRA du
   personnage entraîné sur 6–10 images (LTX Trainer est déjà dans le dépôt
   amont). Coût d'entraînement : < 1 h de H100.
5. **Lip-sync français** : ajuster `audio_cfg` (plage recommandée 3–5),
   `ref_img_index`/`mask_frame_range` pour supprimer les gestes répétés, et
   `exaggeration` côté voix.
6. **Verrouiller les plans acceptés** : aujourd'hui un plan peut être régénéré et
   l'ancienne prise remplacée par erreur. Ajouter un état `approved` (verrou) qui
   empêche l'écrasement et remonte la liste des prises dans l'export.
   *Impact* : évite de perdre les meilleures prises — coût réel ≈ zéro.

## Bloc 3 — Réduire le coût par vidéo acceptée

7. **Générer d'abord en `distilled`, valider le cadrage sur une image clé, puis
   DFR** : la moitié des essais ratés en cadrage ne devraient jamais coûter une
   passe DFR. Mécanique : un mode « brouillon » explicite dans l'UI.
8. **Retake plutôt que régénération** : l'API existe (`/shots/{id}/retake`), mais
   l'UI n'expose pas encore la sélection de zone. C'est le prochain ajout UI
   rentable : un passage raté sur 8 s ne doit coûter que 2 s.
9. **Mise en cache des prompts identiques** (même prompt + même graine = même
   coût évité) : simple, mais ne pas le construire avant d'avoir mesuré combien
   de générations sont réellement dupliquées.

## Bloc 4 — Réduire l'intervention humaine

10. **Préflight automatique avant de payer un GPU** : vérifier que chaque plan a
    un dialogue (avatars), un prompt, une image de référence et une durée
    cohérente. Aujourd'hui l'erreur apparaît dans le job, après la mise en route.
11. **Reprise automatique bornée** : relancer une fois un job échoué pour une
    raison transitoire (OOM, coupure réseau), jamais une raison de fond.
12. **Génération en lot d'un storyboard entier** avec file respectant
    `PVS_MAX_WORKERS=1`, déjà supportée par la base mais pas exposée dans l'UI.

## Bloc 5 — Finition du studio (après les jalons 1–3)

13. Comparateur de prises côte à côte (aujourd'hui : un menu déroulant).
14. Sélection d'une zone de timeline pour le Retake (voir 8).
15. Habillage : titres animés (ASS est déjà en place), logo, safe zones vérifiées.
16. Captures d'écran : assistant d'enregistrement (script d'enregistrement
    d'écran ffmpeg + réimport automatique) — à faire quand
    l'import manuel devient le goulot d'étranglement, pas avant.
17. Multi-utilisateur / authentification : à faire **le jour** où deux personnes
    produisent en même temps. Pas avant.

## Ce qui ne sera pas construit (décisions, pas oublis)

- Framework d'agents, gestionnaire de plugins, système de prompts à étages.
- Orchestrateur de pods / autoscaling : inutile pour 5 vidéos par semaine.
- Détection IA « fiable » des visages déformés : promesse intenable aujourd'hui ;
  la checklist humaine est conservée.
- Intégration de dix moteurs. Deux moteurs vidéo mesurés valent mieux que huit
  adaptateurs non testés.
- Musique générée par IA : une bibliothèque de morceaux libres de droits donne un
  meilleur résultat pour zéro GPU.

## Tableau de bord à suivre (dès la première vidéo réelle)

| Indicateur | Où | Cible initiale |
|---|---|---|
| Plans acceptés sans correction | `/api/projects/{id}/cost` + `shots.status` | > 60 % |
| Tentatives par plan accepté | `attempts_per_success` | < 1,8 |
| Temps de production (humain) | hors studio, à noter | < 45 min / vidéo de 35 s |
| Coût GPU par export | `cost_per_export_usd` | < 1,50 $ |
| Défauts QC détectés après montage | `exports.qc` | 0 |
| Temps de montage | log de job | < 90 s |
