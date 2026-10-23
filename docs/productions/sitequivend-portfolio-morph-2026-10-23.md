# SiteQuiVend — deux films portfolio (morph), 23 octobre 2026

Deux publicités verticales premium construites autour de transitions morph, en
remplacement des premiers tests courts. **`luxury-take-1.mp4` n'a ni été utilisé
ni terminé.**

| # | Film | Durée | Morphs | QC |
| --- | --- | --- | --- | --- |
| 1 | Food & Luxe | 27,60 s | 4 | pass |
| 2 | Automotive & Lifestyle | 26,70 s | 3 | pass |

## Fichiers livrés

`data/portfolio-2026-10-23/exports/` (hors Git : médias lourds, dossier ignoré)

| Fichier | Taille | Contenu |
| --- | ---: | --- |
| `sitequivend-food-luxe.mp4` | 35,0 Mo | signé (end card SiteQuiVend) |
| `sitequivend-food-luxe-sans-signature.mp4` | 37,4 Mo | sans habillage |
| `sitequivend-food-luxe-cover.jpg` | 0,42 Mo | miniature 1080×1920 |
| `sitequivend-automotive-lifestyle.mp4` | 36,4 Mo | signé |
| `sitequivend-automotive-lifestyle-sans-signature.mp4` | 38,5 Mo | sans habillage |
| `sitequivend-automotive-lifestyle-cover.jpg` | 0,77 Mo | miniature 1080×1920 |
| `*.qc.json`, `*.json` | — | contrôle automatique + métadonnées complètes |

Signatures SHA-256, probes et limites : `exports/*.json` et
`docs/productions/sitequivend-portfolio-morph-2026-10-23.json`.

## Structure des deux films

**Food & Luxe — 27,6 s, 4 morphs**

| Temps | Plan | Transition vers le suivant |
| --- | --- | --- |
| 0,0–4,8 | jante chromée, macro studio, balayage spéculaire | **spin** (1,1 s) : la jante accélère et traverse le plan |
| 3,7–10,7 | assiette gastronomique, plongée, vapeur | **zoom** (1,5 s) : on tombe dans l'assiette, on ressort du crema |
| 9,2–14,6 | tasse espresso, crema, vapeur | **spin** (1,0 s) : le crema tourne et devient le dôme |
| 13,6–21,4 | macro chocolat, reflet de fenêtre, coulant | **bloom** (1,6 s) : la lumière du reflet devient l'exposition |
| 19,8–27,6 | plan héros, bokeh, end card à 24,6 s | — |

**Automotive & Lifestyle — 26,7 s, 3 morphs**

| Temps | Plan | Transition vers le suivant |
| --- | --- | --- |
| 0,0–5,8 | lunettes de sport, reflet de route côtière | **zoom** (1,7 s) : on plonge dans la route du reflet |
| 4,1–13,1 | route côtière, GT générique, golden hour | **bloom** (1,5 s) : le soleil rasant devient le reflet de la jante |
| 11,6–18,2 | jante, rotation du cadre, lumière froide | **zoom** (1,5 s) : traversée du moyeu |
| 16,7–26,7 | plan héros, end card à 23,7 s | — |

## Moteurs réellement utilisés

- **Image** : moteur `morphfilm` du dépôt (CPU, Python/OpenCV/NumPy) — plaques
  photographiques, caméra virtuelle 2.5D (zoom, travelling, roulis, parallaxe
  estimée, dérive de mise au point, respiration « caméra épaule » qui s'annule
  aux extrémités pour ne pas casser un raccord), couches d'atmosphère
  procédurales (vapeur, poussière, flares, balayages spéculaires), étalonnage
  cinéma unique, grain, halation, vignettage, encodage x264 CRF 16.
- **Plaques** : générées avec l'outil imagegen (six visuels, aucun logo ni texte,
  véhicule volontairement générique).
- **Montage et QC** : timeline et rendu de `morphfilm`, contrôle
  `backend.app.qc.inspect_export` du studio existant.
- **Audio** : score original synthétisé (numpy/scipy) — nappes, arpèges FM, sub,
  whooshs, impacts, riser, shimmer, calés sur les transitions. Aucun sample tiers.
- **LTX-2.5 / Modal `kulejean567`** : **non exécuté**. `api.modal.com` et
  `modal.com` sont bloqués depuis l'environnement de build (TLS fermé sur chaque
  requête, vérifié le 23/10) et aucun jeton Modal n'y est présent. Le passage GPU
  est écrit et prêt : `scripts/portfolio/ltx_shots.py` (prompts plan par plan,
  reprise sans re-rendu, vérification 1080×1920, coût estimé).

## Contrôle qualité mesuré

| Contrôle | Food & Luxe | Automotive |
| --- | --- | --- |
| Conteneur | H.264 High, 1080×1920, 30 fps, 828 images | H.264 High, 1080×1920, 30 fps, 801 images |
| Durée | 27,60 s (= attendu) | 26,70 s (= attendu) |
| Audio | AAC stéréo 48 kHz, -14,1 LUFS | AAC stéréo 48 kHz, -14,0 LUFS |
| Noirs / images figées | 0 / 0 | 0 / 0 |
| Ratio | 0,562 (9:16 exact) | 0,562 |
| Verdict QC | pass | pass |

Les deux exports ont aussi été relus image par image aux points de morph
(planches-contact de 7 positions par transition) et aux extrémités : chaque
morph est **exact** à w=0 et w=1, sans ghosting. Une planche de contrôle
couvrant les sept transitions est conservée dans
`data/portfolio-2026-10-23/stills/all-morphs.png`.

## Ce qui a été refait après la première revue

La première version livrée était montée et techniquement propre, mais la revue
image par image a montré trois défauts réels, corrigés dans cette révision :

1. **Ouverture auto** : le `portal` (ouverture en forme de lentille) ne
   fonctionnait pas, parce que le plan « lunettes » est un macro où la lentille
   remplit déjà tout le cadre — l'ouverture n'avait aucune place pour grandir et
   se lisait comme un cut. Remplacé par un **zoom dans la route du reflet** : le
   reflet *est* la scène suivante, donc la continuité est dans le contenu.
2. **`bloom` macro → hero** : le flou de zoom radial du plan entrant dupliquait
   le rebord de l'assiette à chaque échantillon et imprimait des anneaux
   fantômes. Remplacé par une **rampe de mise au point** (le plan arrive flou et
   se stabilise) qui ne crée aucune structure parasite.
3. **Rythme** : l'ouverture jante était trop statique et trop longue, la jante
   auto trop molle. Plans raccourcis et mouvements renforcés (zoom + roll +
   travelling), plus une respiration caméra sur toute la durée.

## Coût

- **Modal : 0,00 USD.** Aucun GPU n'a été lancé.
- Rendu local : ~14 min de CPU par film (2 cœurs) pour cette révision, soit
  ~28 min ; non facturé.
- Estimation si le passage LTX était lancé tel quel : **~0,40 USD par film**
  (5 et 4 clips, 22 s de GPU par seconde de vidéo finale — mesure de la
  production du 23/10 —, L40S à 1,95 USD/h, hors démarrage de conteneur).

## Limites observées

1. Plaques générées en 768×1376, remontées en 1080×1920 (×1,4). Le grain et une
   accentuation compensent, mais ce n'est pas une captation native.
2. Mouvement 2.5D : caméra, parallaxe estimée, atmosphère procédurale. Pas de
   mouvement de sujet réel (pas de roue qui tourne en continu, pas de voiture qui
   avance), contrairement à ce que produirait LTX. Le plan « route » de 9 s est
   le plus exposé à cette limite : la voiture est immobile.
3. Les morphs sont des effets de montage — rotation/zoom/portail/flare — et non
   des interpolations de modèle. Le raccord est net aux extrémités, mais il n'y a
   pas de transformation continue de forme entre deux objets comme le ferait un
   morph de réseau de neurones. C'est le compromis assumé pour éviter le ghosting
   qu'un fondu aurait produit entre une jante et une assiette.
4. `macro → hero` réutilise la même assiette : la fin est un plan héros, pas un
   nouveau dessert.
5. Les deux vidéos sont des démonstrations créatives : les véhicules et les plats
   sont illustratifs, pas des réalisations clients.
6. `spin` repose sur un flou de mouvement assumé pendant ~4 images sur 33 : c'est
   ce qui vend la vitesse, mais c'est visible en pause.

## Ce que je referais en priorité

1. Lancer `ltx_shots.py` sur Modal pour remplacer les plaques par de vraies
   séquences animées, puis reconstruire le même montage : c'est le seul vrai saut
   de qualité qui reste, pour ~0,80 USD au total.
2. Passer les plaques en 1280×2304 natif (ou générer directement en 9:16 haute
   résolution) pour supprimer le facteur 1,4.
3. Faire relire les deux films par un tiers : mon regard a construit les morphs,
   il n'est pas neutre sur leur efficacité.
