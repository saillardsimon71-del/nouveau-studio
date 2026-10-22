# Benchmarks — protocole et état

Objectif : décider **avec des fichiers vidéo en main**, pas avec des impressions.
Trois tests de référence, définis dans `benchmarks/scenarios/` :

| Test | Fichier | Question à laquelle il répond |
|---|---|---|
| A — Avatar premium | `test_a_avatar.yaml` | un présentateur français crédible est-il atteignable ? |
| B — Plan cinématographique | `test_b_cinematic.yaml` | une image publicitaire haut de gamme est-elle atteignable ? |
| C — Identité | `test_c_identity.yaml` | le même personnage survit-il à trois plans différents ? |

## État réel (2026‑10‑22)

| Étape | État |
|---|---|
| Scénarios écrits, conditions identiques entre moteurs | ✅ |
| Runner + mode `--dry-run` (validation, estimations) | ✅ |
| Estimations de coût calculées | ✅ `benchmarks/results/plan_2026-10-22.json` |
| **Générations réelles** | ⏳ **non exécutées** — aucun GPU dans l'environnement de développement |
| Scores visuels | ⏳ à renseigner à la main après visionnage |

Le runner **refuse** de lancer un benchmark si l'API ne présente aucun moteur réel
disponible : mesurer la simulation produirait des chiffres faux. C'est
volontaire — un benchmark qui ment est pire que pas de benchmark.

## Estimations (à confirmer par la mesure)

Extraits de `benchmarks/results/plan_2026-10-22.json`. Les GPU-secondes par
seconde de vidéo sont des hypothèses issues des vitesses publiées par les
auteurs (LTX DFR ≈ 90–150 s pour un clip de 5 s sur H100 ; distilled ≈ 20–40 s ;
LongCat 720p ≈ 40–80 s pour 8 s sur A100 ; Wan TI2V‑5B ≈ 10–20 s).

| Test | Moteur | GPU | GPU·s estimées | Coût estimé |
|---|---|---|---|---|
| A | longcat_avatar | A100 80 Go | ~64 | ~0,03 $ |
| A | ltx_native (two_stages) | H100 | ~144 | ~0,12 $ |
| A | infinite_talk | A100 80 Go | ~96 | ~0,04 $ |
| B | ltx_native (DFR) | H100 | ~150 | ~0,12 $ |
| B | ltx_native (distilled) | H100 | ~42 | ~0,03 $ |
| B | comfyui | RTX 5090 | ~60 | ~0,02 $ |
| B | wan22_ti2v (TI2V‑5B) | RTX 4090 | ~18 | ~0,003 $ |
| C | longcat_avatar | A100 80 Go | ~32 | ~0,01 $ |
| C | ltx_native (DFR) | H100 | ~100 | ~0,08 $ |

Lecture utile : sur une pub de 35 s (≈ 5 plans, 2 avatars + 3 B‑roll), l'ordre de
grandeur est **0,15–0,40 $ de GPU par vidéo** hors échecs. Le poste de coût
dominant n'est donc pas le GPU mais **le nombre de tentatives** — d'où
l'importance du Retake ciblé et du QC.

## Comment lancer

```bash
# 1. planifier sans GPU (fonctionne partout)
make bench-dry
python benchmarks/run_benchmark.py --scenario test_a_avatar --dry-run

# 2. sur une machine GPU, studio configuré et moteurs disponibles
python benchmarks/run_benchmark.py --scenario test_a_avatar --api http://127.0.0.1:8000 \
    --json benchmarks/results/test_a_run1.json
```

Le runner crée un projet, applique le storyboard du scénario, soumet chaque
variant au studio (le même chemin de code que la production), attend la fin,
puis écrit un enregistrement par variant : moteur, paramètres, statut, secondes
GPU, coût, identifiant de job, erreur éventuelle.

## Ce qui est mesuré automatiquement

- lecture du conteneur, codec, résolution, fps, durée réelle ;
- présence et caractéristiques de la piste audio ;
- segments noirs (`blackdetect`), images figées (`freezedetect`) ;
- loudness intégrée (EBU R128) ;
- cohérence durée demandée / durée obtenue.

## Ce qui reste humain (et pourquoi)

Identité du visage, précision du lip-sync, naturel des expressions, respect du
prompt, qualité de la voix. Ces jugements ne sont pas automatisables de façon
fiable aujourd'hui ; les simuler donnerait une fausse assurance. Le studio les
présente comme une checklist attachée au clip, avec une échelle 0–5 et un seuil
d'échec par critère.

Méthode de notation recommandée : visionnage à vitesse normale **puis** à 0,25×
sur les zones de bouche, et comparaison côte à côte des variants dans le même
lecteur.

## Critères de décision (écrits avant les résultats)

- **Test A** : identité/lip-sync/voix ≥ 3/5, aucune déformation visible sur 3
  lectures. Sinon, le moteur n'entre pas en production.
- **Test B** : photoréalisme, mouvement et artefacts ≥ 4/5 sur au moins 2 essais
  sur 3, coût par seconde acceptée < 0,60 $.
- **Test C** : identité reconnue sans hésitation par 2 relecteurs indépendants sur
  les 3 plans, tenue inchangée.

## Reproductibilité

- Même image de référence (`benchmark_assets/character_reference.png`) pour tous
  les plans et tous les moteurs.
- Même texte prononcé, même échantillon de voix pour les tests A et C.
- Graines fixées dans les scénarios (`seed` par défaut 42 hors avatar).
- Les paramètres exacts sont recopiés dans le résultat, pas résumés.
- L'export conserve `filtergraph.txt` et `engine.log` de chaque job : un rendu
  contesté peut être rejoué.

## Défauts déjà observés pendant la construction (corrigés)

Ces défauts ont été trouvés en inspectant les frames réelles, pas en relisant le
code — c'est la raison pour laquelle le test d'export vérifie la présence de
pixels clairs dans l'image :

1. **Sous-titres en double** : le moteur de simulation incrustait le dialogue,
   puis le montage l'incrustait à nouveau. Règle adoptée : un moteur livre une
   **plaque propre** ; tout le texte relève de la post-production.
2. **Export refusé en cascade** : un seul plan avec un flux à débit variable
   faisait échouer tout le graphe `xfade`. Correction : normalisation en deux
   passes vers des fichiers intermédiaires à fps constant.
3. **Timeline plus courte que prévu** : un plan avatar se raccourcissait à la
   durée du clip audio simulé (27 s au lieu de 34 s). Correction : la durée du
   plan est une décision éditoriale, l'audio est complété par du silence.
