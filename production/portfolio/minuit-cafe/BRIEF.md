# MINUIT CAFE — spot concept produit (24 octobre 2026)

## Objectif
Produire **un spot publicitaire fictif de 15 secondes** pour le portfolio SiteQuiVend, sans prétendre qu'il s'agit d'un client réel ni d'un produit disponible à la vente. Univers : café premium, lumière noire et cuivrée, photo vraie, mouvements crédibles.

## Recette
- 3 photos réelles de Pexels en 9:16 (768x1344), préparées par `scripts/production/portfolio_minuit_cafe.py prepare`.
- 3 plans **image-to-video LTX-2.5 Distilled** sur Modal, app séparée `pvs-ltx`, GPU L40S, volume de modèles existant `studio-ltx25-models` monté en lecture seule.
- Trois appels maximum, un par scène, 5 secondes générées chacun, 4 secondes retenues par plan ; **sans retry automatique**. Si un plan échoue, l'export échoue sans substituer de photos fixes.
- Montage 12 secondes de plans + carte de marque 3 secondes, 48 fps par interpolation depuis les 24 fps natifs, 1080x1920, piste musicale, MP4, miniature, manifeste, crédits et images sources.
- Contrôle QC automatique ffprobe ; revue humaine indispensable (mouvement, défauts, esthétique, droits).

## Storyboard
| Secondes | Image Pexels | Animation | Texte |
|---|---|---|---|
| 0–4 | Macro grains torréfiés | Lent travelling macro, reflets ambrés | Aucun texte généré |
| 4–8 | Extraction expresso | Écoulement naturel, caméra latérale | Aucun texte généré |
| 8–12 | Tasse d'expresso | Subtiles volutes de vapeur | Aucun texte généré |
| 12–15 | Carte de fin créée au montage | Marque fictive « MINUIT » | « LE CAFE, AUTREMENT » + crédit SiteQuiVend |

## Sources photographiques
1. Marcus Echo, [grains torréfiés](https://www.pexels.com/photo/close-up-of-roasted-coffee-beans-on-dark-background-36722820/)
2. James Collington, [extraction expresso](https://www.pexels.com/photo/close-up-of-espresso-pouring-from-coffee-machine-30818517/)
3. Alex Souza, [tasse d'expresso](https://www.pexels.com/photo/cup-of-espresso-on-a-saucer-20884081/)

Photographies sous [licence Pexels](https://www.pexels.com/license/) : transformation/publicité permises, sans faux soutien de personnes ou marques. Pour la musique « Ascension » de Scott Buckley, [licence CC BY 4.0](https://www.scottbuckley.com.au/library/ascension/) ; conserver les crédits en publication.

## Exécution & dépenses
Workflow : `.github/workflows/portfolio-minuit-cafe.yml` sur la branche `production/portfolio-minuit-cafe-20261024`. Seul le message de commit `RUN_PORTFOLIO_MINUIT_CAFE_ONCE_20261024` déclenche les trois appels Modal automatiquement via push ; les autres commits ne consomment aucun GPU. Délai GPU par appel plafonné à 480 s, pas de second essai automatique, ressources éphémères et volume en lecture seule. **Coût final réel à vérifier côté Modal**, ne pas présenter l'estimation comme une facture.

## Livrables attendus
GitHub Actions → run de `Portfolio | MINUIT CAFE 15s (Pexels + LTX)` → artefacts `MINUIT-CAFE-Pexels-references`, `MINUIT-CAFE-LTX-source-shots`, `MINUIT-CAFE-15s-LTX`. Fichier final `MINUIT-CAFE-Spot-15s-LTX.mp4`. Le spot reste un *spec ad* non commandé.
