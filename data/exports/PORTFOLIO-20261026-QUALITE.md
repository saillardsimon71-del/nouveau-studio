# Portfolio SiteQuiVend - 26 octobre 2026

| Film | Durée | Master 1080 x 1920 | Web 720 x 1280 |
|---|---:|---:|---:|
| ÉCLAT 02 | 15,50 s | 9,55 Mo | 1,74 Mo |
| PULSE 01 | 13,25 s | 8,25 Mo | 1,50 Mo |

Les quatre fichiers sont de vrais MP4 H.264, yuv420p, 24 i/s, avec audio AAC
stéréo 48 kHz et démarrage rapide. Les masters sont agrandis et recadrés depuis
les rendus H3 natifs de 768 x 1344. Les versions web conservent le son.

## Contrôle qualité effectué

- Décodage intégral des quatre exports, sans erreur. 372 images pour ÉCLAT,
  318 pour PULSE. Durées des pistes vidéo et audio contrôlées séparément.
- Inspection visuelle de chaque plan par planches à 4 images/s, puis des deux
  montages complets à 2 images/s, avec arrêts sur image en pleine résolution
  pour les produits, la peau et les poignets des gants.
- ÉCLAT : verre et goutte cohérents dans les images inspectées, visage stable,
  packshot droit et fermé, étiquette blanche conservée sans texte ajouté.
- PULSE : même athlète et tenue, montée sur haltères cohérente, gants stables.
  Deux petits marquages de poignets ont été retirés par retouche suivie sur CPU.
- Aucun défaut majeur repéré dans cette inspection par échantillonnage.
  Ce contrôle ne constitue pas une revue manuelle de chaque image.
- Audio vérifié par décodage et mesure : ÉCLAT -15,9 LUFS / crête -3,4 dBFS ;
  PULSE master -16,5 LUFS / crête -2,6 dBFS, web -16,6 LUFS / -2,5 dBFS.
  Le contrôle audio est technique ; aucune écoute critique en temps réel
  n'est déclarée. La bande-son assemble musique instrumentale et bruitages
  originaux de verre, d'air et d'impact. La piste native H3 est écartée.

## Production et finition

Référence récupérée : MAISON 01, son MP4 et son rapport de génération.
Même worker Modal H3 existant, GPU L40S, 20 étapes, échantillonneur
res_multistep et calendrier simple. Aucun redéploiement du worker.

Six plans générés en deux lots. **Zéro régénération GPU.** Temps des fonctions
de génération : 39,4 min pour ÉCLAT, 32,6 min pour PULSE, environ 72 min au total.
Ce temps n'est pas une facture Modal.

ÉCLAT comporte trois plans animés et une signature, avec fondus courts.
Le cadrage sur la joue est resserré pour conserver la cohérence du produit.
PULSE comporte quatre plans montés, dont un insert matière issu d'une portion
inutilisée du premier rendu, puis une signature. Les effets sonores suivent les
coupes. Les exports utilisent un format couleur uniforme compatible web.

## Fichiers et sources

- `ECLAT-02/` et `PULSE-01/` : master, version web, couverture, planche et crédits.
- `SOURCES/` : photographies réelles originales, images initiales préparées,
  six clips H3, musiques, bruitages originaux et rapports de génération.
- `SOURCES.json` : URLs, auteurs, licences indiquées par les fournisseurs,
  cadrages, prompts, seeds et empreintes des images.
- `VERIFICATION.json` : mesures et SHA-256 des quatre MP4 livrés.

Films de concept indépendants. Musiques : "Reverie" et "Catalyst" de
Scott Buckley, déclarées CC BY 4.0 par leur auteur. Les crédits complets sont
dans les deux dossiers et doivent accompagner une publication utilisant ces pistes.

## GitHub

- [Précontrôle CPU](https://github.com/saillardsimon71-del/nouveau-studio/actions/runs/40291747686)
- [Production des six plans H3 et premiers montages](https://github.com/saillardsimon71-del/nouveau-studio/actions/runs/40292105062)
- [Finition définitive CPU et quatre MP4](https://github.com/saillardsimon71-del/nouveau-studio/actions/runs/40302562256)
- [PR dédiée non fusionnée](https://github.com/saillardsimon71-del/nouveau-studio/pull/12)

Le site SiteQuiVend.fr, les vidéos de prospection et les autres moteurs n'ont
pas été modifiés. Aucun nouvel agent n'a été utilisé.
