# data/

Contenu local, non versionné (sauf `exports/`).

| Dossier | Contenu |
|---|---|
| `projects/<id>/jobs/<job>/` | sorties brutes des moteurs : clips, voix, sous-titres ASS/SRT, `filtergraph.txt`, `engine.log` |
| `uploads/` | fichiers importés (captures d'écran, vidéos, échantillons de voix) |
| `tmp/` | logs de jobs |
| `assets/music/` | musiques libres de droits déposées à la main |
| `exports/` | exports publiés volontairement dans le dépôt (démonstrations) |

`studio.db` (SQLite) contient projets, plans, jobs, artefacts, exports et coûts.
Sauvegarde = copier `data/` entier ; restauration = le remettre en place.

## Contenu versionné

- `exports/demo_simulation_vertical.mp4` — export réel du studio, **100 % simulation**
  (aucun modèle IA) : il démontre le pipeline (plans, enchaînement, sous-titres
  incrustés, mixage, loudness, QC), pas la qualité des modèles.
- `exports/frame_*.png` — images extraites de cet export.
