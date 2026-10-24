# NOIR / 01 — publicité conceptuelle (2026-10-24)

**Statut :** pipeline GitHub prêt, ne signifie pas validation artistique. Brand fictive, aucune commande client revendiquée.

## Décision source
La photo initialement proposée par Meta AI, Pexels 8178744 « Amber & Orchid » (Muhammad Younas), était **sur fond blanc, porte une inscription réelle, et ne correspond pas à la direction noire**. Elle est exclue.

Source retenue après vérification visuelle : photo [7814730](https://www.pexels.com/photo/water-drops-on-an-ornate-glass-bottle-7814730/) par **Mikhail Nilov**, flacon transparent sans étiquette, posé en diagonale sur une surface noire mouillée. [Licence Pexels](https://www.pexels.com/license/). La photo source est une photographie réelle, pas une image générée. Trois recadrages de la **même image** préservent l'identité du flacon. La direction artistique suit la pose réelle (flacon couché) : ne pas inventer un flacon debout ni une piscine noire qui n'existe pas.

## Storyboard final
| Temps nominal | Plan | Animation |
|---|---|---|
| 0–5 s | Révélation, flacon sur sol humide | Petit dolly-in, lumière cuivrée, verre rigide |
| 5–10 s | Macro gouttelettes et verre | Focus pull et léger parallax, pas de déformation |
| 10–15 s | Packshot stable | Lent dolly-out, reflets sur gouttes existantes |
| 15–18 s | Carte de fin ajoutée en postproduction | NOIR / 01 — « Laissez une empreinte. » — « Création conceptuelle — SiteQuiVend.fr » |

## Infrastructure
- Branche : `production/portfolio-noir-01-20261024`
- Workflow : `.github/workflows/portfolio-noir-01.yml`
- Recette : `scripts/production/portfolio_noir_01.py`
- LTX-2.5 Distilled / ComfyUI existants : `deploy/modal_ltx_worker.py`
- Entrypoint **confirmé** : `modal run deploy/modal_ltx_worker.py --mode render ... --image-png <fichier> --out <fichier>`
- Modal : workspace `kulejean567`, application `pvs-ltx`, GPU `L40S`, volume `studio-ltx25-models` **en lecture seule**.
- Maximum 3 appels GPU de 5 s demandées, pas de relance automatique. Pas de modification de `main`, pas de modèle redownloadé.
- Génération 24 fps native. Livraison 1080×1920 à 48 fps interpolées, montage FFmpeg, extrait de musique [« Ascension » de Scott Buckley](https://www.scottbuckley.com.au/library/ascension/) CC BY 4.0 **à créditer**.
- Artefacts GitHub : `NOIR-01-Pexels-references`, `NOIR-01-LTX-source-shots`, `NOIR-01-18s-LTX` avec MP4, couverture, crédits, manifeste.
- Garde-fou : un commit au message exact `RUN_PORTFOLIO_NOIR_01_ONCE_20261024` sur un fichier surveillé déclenche l'exécution. Tout autre commit se limite au préflight ou est ignoré. Une exécution manuelle demande `stage=render` et `confirm_spend=oui`.

## Critères d'acceptation
1. Origine Pexels et musique documentées.
2. Vrais MP4 LTX générés avec présence vérifiée via ffprobe (pas de photo fixe substituée).
3. Trois plans assemblés + vraie carte de marque, aucun écran noir, rapport machine.
4. **Revue humaine** des déformations, identification du produit, typographie et interpolation avant publication commerciale. Un « success » GitHub ne signifie pas « validé artistiquement ».
