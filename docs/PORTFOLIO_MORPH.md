# Portfolio SiteQuiVend — deux films premium avec transitions morph

Deux publicités verticales de 26 à 28 secondes construites sur des morphs, avec
le studio existant comme socle et **aucune modification de l'ancien Studio IA**.

| Film | Durée | Format | Morphs | Statut |
| --- | --- | --- | --- | --- |
| Food & Luxe | 27,6 s | 1080×1920, 30 fps | 4 | rendu, QC au vert |
| Automotive & Lifestyle | 26,7 s | 1080×1920, 30 fps | 3 | rendu, QC au vert |

## Ce qui a été réellement utilisé

**Images de départ** : six photographies publicitaires générées avec l'outil
imagegen (jante, assiette gastronomique, macro chocolat, tasse espresso,
lunettes de sport avec reflet de route, route côtière avec véhicule générique).
Aucune image de marque réelle, aucun texte, aucun watermark. Les prompts exacts
sont conservés dans `exports/*.json` (`prompts`).

**Mouvement** : moteur `morphfilm` (ce dossier), 100 % CPU, Python/OpenCV/NumPy.
Chaque plan est une plaque photographique overscannée avec une caméra virtuelle
(zoom, travelling, roulis, parallaxe estimée, dérive de mise au point, plus une
respiration « caméra épaule » dont l'enveloppe s'annule aux deux extrémités pour
ne jamais casser un raccord) et des couches d'atmosphère procédurales : vapeur
qui monte, poussière dans la lumière, balayages spéculaires, flares. L'étalonnage, le grain, le halos et le vignettage
sont appliqués une seule fois par image, à la fin, pour que les morphs ne
blendent jamais deux structures de grain différentes.

**Morphs** : trois opérateurs choisis pour ce que les deux plans partagent
vraiment.

| Transition | Film | Opérateur | Pourquoi |
| --- | --- | --- | --- |
| jante → assiette | Food | `spin` | la jante accélère, traverse le plan en tournant, l'assiette arrive encore en rotation : aucun fondu, jamais deux images superposées |
| assiette → tasse | Food | `zoom` | on tombe dans le cercle de l'assiette et on ressort du crema de la tasse |
| tasse → macro | Food | `spin` | le crema tourne et devient le dôme de chocolat |
| macro → hero | Food | `bloom` | le reflet devient une exposition qui se rouvre sur le plan final |
| lunettes → route | Auto | `zoom` | on plonge dans la route du reflet et on ressort sur la route réelle : le reflet *est* la scène suivante |
| route → jante | Auto | `bloom` | le soleil rasant devient le reflet de la jante |
| jante → hero | Auto | `zoom` | traversée du moyeu vers le plan héros |

Les ancres (cercles, ellipses) sont mesurées sur les plaques natives puis
projetées par l'inverse exact de la transformation caméra
(`anchors.py`), et vérifiées visuellement sur les images-repères avant rendu
(`python -m scripts.portfolio.build --film food --debug-circles`).

**Audio** : score original synthétisé (numpy/scipy) — nappes, arpèges FM,
sub, whooshs, impacts, riser, shimmer — calé sur les transitions. Aucun sample
tiers, donc aucune licence à créditer. Normalisé à -14 LUFS, crête vraie -5 dBTP.

**Aucun GPU n'a été facturé.**

## Pourquoi pas LTX-2.5 sur ce passage

LTX-2.5 / Modal `kulejean567` est bien l'infrastructure du dépôt
(`deploy/modal_ltx_worker.py`, app `pvs-ltx`), et le chemin GPU est écrit :
`scripts/portfolio/ltx_shots.py`. Il n'a **pas pu être exécuté ici** :

- `api.modal.com` et `modal.com` sont bloqués depuis l'environnement de build
  (handshake TLS fermé sur chaque requête sortante, vérifié) ;
- aucun jeton Modal n'est présent localement (`~/.modal.toml` absent) ;
- `raw.githubusercontent.com` est également bloqué.

Le script est prêt, avec ses prompts plan par plan et son estimation de coût
mesurée (~22 s de GPU par seconde de vidéo finale, soit ~0,40 USD par film sur
L40S). Il suffit de le lancer depuis une machine avec accès Modal :

```bash
modal profile activate kulejean567
python -m scripts.portfolio.ltx_shots --film food --dry-run   # 0 GPU, plan + coût
python -m scripts.portfolio.ltx_shots --film food             # rendu réel
python scripts/portfolio/build.py --film food --full          # même montage
```

Le montage est identique : les clips LTX remplacent les plaques plan par plan,
la timeline et les morphs restent les mêmes.

## Reproduire

```bash
pip install numpy opencv-python-headless pillow scipy imageio-ffmpeg
export PYTHONPATH=.

# 1. dériver la jante « auto » depuis la jante « food » (re-cadrage + grade froid)
python -m scripts.portfolio.morphfilm.derive

# 2. vérifier les ancres de morph sur les images de fin/début de plan
python -m scripts.portfolio.build --film both --debug-circles

# 3. planches-contact de chaque morph (le contrôle le moins cher)
python -m scripts.portfolio.build --film both --sheets

# 4. rendu complet (image + score + mux + QC + cover + métadonnées)
python -m scripts.portfolio.build --film food --full
python -m scripts.portfolio.build --film auto --full

# 5. retoucher le son, le cover ou les textes sans refaire le rendu image
python -m scripts.portfolio.build --film food --finish
```

Le rendu image prend ~12 min par film sur 2 cœurs CPU (1080×1920, 30 fps,
étalonnage, grain et encodage x264 CRF 16).

## Fichiers

```
scripts/portfolio/
  build.py                CLI : debug, planches, stills, score, finish, full
  ltx_shots.py            passage LTX-2.5 (Modal pvs-ltx), prompts + coût
  measure_features.py     mesure des formes sur les plaques natives (outil)
  morphfilm/
    imageops.py           chargement, étalonnage cinéma, grain, bloom, halation
    camera.py             plaque overscannée, caméra sub-pixel, parallaxe, DOF
    anchors.py            ancres natives → projection exacte sur l'image de rendu
    features.py           détecteur cercle/ellipse (score médian de gradient)
    morph.py              spin / zoom / portal / bloom / flow / radial
    atmos.py              vapeur, poussière, flares, balayages spéculaires
    score.py              synthèse musicale et sound design
    film.py               timeline, rendu image par image, end card, mux, QC
    films.py              les deux montages : plans, mouvements, morphs, prompts
    derive.py             plaques dérivées, reproductibles
tests/test_portfolio_morphfilm.py   23 tests : endpoints, projection, timeline, score
```

Les médias lourds (MP4, WAV, PNG) restent hors dépôt : `data/` est déjà ignoré
par `.gitignore` sauf `data/exports/`.

## Livrables

Dans `data/portfolio-2026-10-23/exports/` :

| Fichier | Contenu |
| --- | --- |
| `sitequivend-food-luxe.mp4` | version signée (end card SiteQuiVend) |
| `sitequivend-food-luxe-sans-signature.mp4` | version sans habillage, pour un prospect |
| `sitequivend-food-luxe-cover.jpg` | miniature 1080×1920 |
| `sitequivend-automotive-lifestyle*.mp4` | idem pour la seconde vidéo |
| `*.qc.json` | contrôle automatique (format, durée, audio, noirs, images figées, loudness) |
| `*.json` | métadonnées complètes : plans, timeline, morphs, moteurs, limites, SHA-256 |

## Limites, dites franchement

- Les plaques sont générées en 768×1376 puis remontées en 1080×1920 (×1,4). Le
  grain et une accentuation compensent, mais ce n'est pas une captation native.
- Le mouvement est un 2.5D : caméra, parallaxe estimée et atmosphère procédurale.
  Il n'y a pas de mouvement de sujet réel, contrairement à ce que produirait LTX.
- Les morphs sont des effets de montage (rotation/zoom/portail/flare), pas des
  interpolations de modèle. Le raccord est exact aux deux extrémités, sans
  ghosting, mais le passage entre les deux images est une traversée, pas un
  changement de forme continu comme un morph de réseau de neurones.
- Le `portal` (ouverture en forme de lentille) a été écrit puis **abandonné
  pour l'ouverture auto** : le plan « lunettes » est un macro où la lentille
  remplit déjà tout le cadre, donc l'ouverture n'avait aucune place pour grandir
  et se lisait comme un cut. La traversée du reflet fait le même travail avec une
  vraie continuité de contenu. L'opérateur reste dans le moteur et reste testé.
- `macro → hero` réutilise la même assiette : la fin est un plan héros, pas un
  nouveau dessert. C'est un choix de montage assumé, pas une découverte.
- La vidéo `luxury-take-1.mp4` n'a pas été utilisée ni terminée, conformément à
  la consigne.
