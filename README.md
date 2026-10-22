# Premium Video Studio

Studio de production vidéo verticale (9:16) assisté par IA : un brief en français
devient un storyboard validé, des plans générés par des modèles ouverts, une voix
française, des captures d'écran réelles, puis une publicité montée, sous-titrée et
mixée — exportable en un fichier.

Ce dépôt n'est pas une démonstration de modèle. C'est l'**environnement de
production** : contrats de moteurs remplaçables, gestion de projets et de plans,
jobs asynchrones, contrôle qualité, régénération ciblée, suivi de coût.

## État en une ligne

LTX-2.5 et LongCat-Video-Avatar 1.5 ont produit de vrais MP4 sur Modal
`kulejean567`. Le premier avatar français mesure 720 x 1280, dure 3,72 s et
contient une piste AAC. Le branchement direct aux jobs du studio est décrit dans
[`docs/MODAL_STUDIO.md`](docs/MODAL_STUDIO.md). Chatterbox et VoxCPM2 restent
des adaptateurs locaux non validés ici ; le parcours Modal utilise la voix
synthétique française Henri.

## Démarrage

```bash
# 1. installer (venv python + dépendances front)
make install

# 2. lancer en développement (API :8000 + UI :5173, proxy /api)
make dev
#    ou : un seul process qui sert UI + API + médias
make run
```

Ouvrir http://localhost:8000 (ou http://localhost:5173 en dev).
Aucune clé n'est nécessaire pour démarrer.

### Vérifier que tout fonctionne, sans GPU

```bash
make test        # 22 tests : pipeline, QC, montage, sous-titres, API
make demo        # crée une pub de 35 s, génère les plans, monte, exporte, affiche le QC
make bench-dry   # plan des 3 benchmarks + estimations de coût GPU
```

`make demo` produit un vrai MP4 vertical de ~34 s (sous-titres incrustés, musique,
enchaînements, loudness normalisée) — construit avec des **plaques de test**, pas
avec de l'IA. Un exemple est versionné :
[`data/exports/demo_simulation_vertical.mp4`](data/exports/demo_simulation_vertical.mp4).

## Parcours utilisateur

1. **Décrire** la vidéo en français (« pub Instagram de 35 s avec mon avatar qui
   présente une automatisation e-mails »).
2. **Storyboard** proposé par le directeur (LLM JSON validé, ou template local),
   modifiable plan par plan.
3. **Générer** un plan : vidéo (LTX), avatar parlant (voix → lip-sync) ou
   **import** d'une vraie capture d'écran.
4. **Contrôler** : QC automatique (format, durée, audio, noirs, images figées,
   loudness) + checklist humaine (identité, lip-sync, jeu).
5. **Régénérer** un plan ou seulement une **zone** (Retake : sélection début/fin,
   réinsertion dans le clip d'origine), puis choisir la meilleure prise parmi les
   artefacts du plan.
6. **Exporter** : enchaînements, sous-titres ASS + `.srt`, musique, loudness
   cible, poster.

## Ce qui existe aujourd'hui

| Domaine | État |
|---|---|
| API + UI (React/TS, sans build exotique) | ✅ fonctionnel, testé |
| Directeur créatif (DeepSeek compatible, JSON strict, retry) | ✅ code + fallback local testé ; **appel LLM réel non exécuté** (pas de clé) |
| Projets / plans / personnages / voix / artefacts | ✅ |
| Jobs asynchrones, progression, reprise après redémarrage, annulation | ✅ |
| Montage ffmpeg (xfade, ASS, mixage, loudnorm, poster, SRT) | ✅ mesuré et vérifié image par image |
| QC automatique | ✅ |
| Coût par job / par export | ✅ |
| Moteurs Modal LTX-2.5 et LongCat 1.5 | MP4 réels générés ; interface directe via les jobs du studio |
| Adaptateurs locaux Chatterbox, VoxCPM2, LTX natif et ComfyUI | Écrits, non validés ici |
| Scripts d'installation GPU + protocole de benchmark | ✅ prêts |

## Documentation

- [`docs/RESEARCH.md`](docs/RESEARCH.md) — sélection technique argumentée
  (LTX-2.5 vs Wan2.2, LongCat 1.5 vs InfiniteTalk, choix de la voix française,
  et la décision motivée sur LTX Desktop).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — contrat de moteur, modèle de
  données, jobs, montage, QC, coûts.
- [`docs/MODAL.md`](docs/MODAL.md) — branchement du compte Modal de Studio IA V2
  (identité, réutilisation des volumes, iPhone → Actions → GPU → MP4)
- [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) — les trois tests de référence, ce
  qui est mesuré automatiquement, ce qui reste humain, protocole reproductible.
- [`docs/GPU.md`](docs/GPU.md) — choix du fournisseur, recettes de pod, volumes
  de poids, contrôle des coûts, reprise après interruption.
- [`docs/STATE.md`](docs/STATE.md) — ce qui marche, ce qui est testé, ce qui reste
  non vérifié, limites observées, coûts.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — prochains gains, ordonnés par impact réel.

## Structure

```
backend/app/       API FastAPI, jobs, QC, coûts, graphes ASS
backend/app/engines/   une classe par moteur (ltx_native, longcat, tts, comfyui, mock, assembly)
frontend/          UI React/TypeScript (Vite)
workflows/         recettes LTX (YAML), entrée avatar (JSON), ComfyUI (README)
benchmarks/        scénarios YAML + runner + résultats
scripts/           dev/run, installation GPU, démo hors-ligne
tests/             pytest (pipeline, montage, sous-titres, API)
docs/              recherche, architecture, benchmarks, état, roadmap
data/              artefacts runtime (non versionnés) + démonstrations publiées
```

## Configuration

Copier [`.env.example`](.env.example) vers `.env`. Les variables importantes :

| Variable | Effet |
|---|---|
| `PVS_LLM_API_KEY` | active le directeur IA (sinon template local) |
| `PVS_LTX_REPO`, `PVS_LTX_MODELS` | rend `ltx_native` disponible |
| `PVS_AVATAR_REPO`, `PVS_AVATAR_WEIGHTS` | rend `longcat_avatar` disponible |
| `PVS_TTS_PYTHON` | interpréteur de l'environnement TTS |
| `PVS_ALLOW_MOCK` | `0` en production : un job échoue au lieu de simuler |
| `PVS_PROVIDER`, `PVS_RATE_*` | tarifs utilisés par le suivi de coût |

## Limites assumées

- Le QC automatique ne juge **pas** la beauté d'un plan : identité, lip-sync et
  jeu restent validés par un humain. C'est un choix, pas un oubli.
- Les scores de qualité des benchmarks sont renseignés à la main après visionnage.
- Un GPU n'est jamais facturé au repos : aucun pod permanent n'est provisionné
  par l'application elle-même.
