# Pilote publicitaire SiteQuiVend — FRAGRANCE / « Un instant, une empreinte »

Date : 23 octobre 2026. **Travail direct dans GitHub, sans Work ni Arena.**

## Diagnostic fondé sur le dépôt

La première publicité de 26 s (`docs/productions/sitequivend-2026-10-23.md` et son JSON) a été créée avec **trois plans LTX image→vidéo contrôlés**, chacun guidé par une image photoréaliste dédiée, et une transformation vidéo→vidéo distincte. Quatre prises GPU au total : 0,39089376 USD Modal. Le montage était construit et titré dans `scripts/production/sitequivend_assemble.py`, avec musique externe identifiée sous licence, voix/sous-titres vérifiés. La preuve porte sur la recette consignée dans GitHub ; les MP4 de Work ne sont pas versionnés.

Les deux publicités narratives ultérieures sur Google Drive ont un problème de **direction, de rythme et de continuité** : gâteau qui change d'état, trop de plans semblables, enchaînements sans intention. Il ne sert à rien de lancer une nouvelle V3 à 30 s.

## Choix créatif

**Une pub fictive de parfum de 12–14 s**, trois plans et **un seul produit**. Elle doit évoquer une publicité de haute parfumerie, et non une démo d'effets génératifs. Univers : verre ambré, pierre anthracite, cuivre et lumière de studio. Aucun nom de marque réelle, aucune promesse marketing invérifiable.

- **0–4 s : le désir.** Flacon seul dans le noir. Un rai de lumière révèle le liquide et les reflets ; travelling avant limité et absolument stable. Nous ne montrons pas de texte en génération.
- **4–8 s : la matière.** Gros plan contrôlé sur le verre et son épaisseur, les petites gouttes et la lumière qui s'y réfracte. Pas de pulvérisation impossible, pas de modification du bouchon.
- **8–12,5 s : la signature.** Le produit devient lisible en entier ; léger arc de caméra, texture de pierre mouillée. Texte minimal **uniquement en postproduction** : « MAKE AN IMPRESSION. » / « AI PRODUCT FILM — DEMO ».

Montage : **coupes franches uniquement**, sans morph, flash, crossfade ni zoom numérique de transition. Chaque changement d'échelle doit être motivé. Bande-son : pas de musique générée ni de piste aléatoire ; premier montage silencieux ou sound design discret, puis morceau sous licence documentée **après** validation du film.

**48 fps minimum en livraison finale** seulement après validation du mouvement, par génération native si le pipeline réel le prend en charge ou interpolation contrôlée ; ne pas changer artificiellement l'étiquette FPS. Le **premier test source reste à 24 fps LTX**, conformément au worker réellement disponible ; on n'essaie pas de résoudre ce point avant d'avoir un plan valable.

## Porte de validation : une seule prise maintenant

Le workflow `.github/workflows/sitequivend-product-pilot.yml` prépare une photographie Pexels libre d'usage commercial, la recadre verticalement et lance **une seule prise LTX guidée par image de 5 secondes**. Il réutilise `deploy/modal_ltx_worker.py`, l'app `pvs-ltx` et les secrets GitHub Modal déjà configurés. Une fois terminé, il publie le MP4, le PNG utilisé et les métadonnées dans les **Artifacts** du run.

- **Pas de renouvellement automatique**, pas de plusieurs variations, pas de longues productions.
- **Budget :** une prise, timeout du worker existant ; coût réel à lire dans le JSON. Ne pas dépasser le plafond utilisateur de 5 USD.
- **Si le téléchargement de l'image échoue, le GPU n'est pas sollicité.**
- **Critères d'acceptation visuelle** : bouteille stable sur cinq secondes, bouchon identique, vrai mouvement de caméra, reflets crédibles, zéro forme parasite, aucune coupure interne. Rejeter si un seul défaut majeur est visible.
- **Si la prise ne passe pas**, il faut repenser référence/cadrage/prompt AVANT tout second calcul.
- **Si elle passe**, préparer deux autres prises seulement, avec références de cadrage spécifiques au même produit, puis monter 12–14 s.

### Source de l'image d'essai

[Albina White — Display of Cosmetic, Pexels #12053223](https://www.pexels.com/photo/display-of-cosmetic-12053223/). Photographie de flacon ambré sur fond sombre. Source stock utilisée comme **visuel de démonstration**, sans affiliation avec la photographe ou un fabricant. Voir [licence Pexels](https://www.pexels.com/license/). La photographie est téléchargée au runtime, pas committée dans Git.

### Technique — précautions

La durée d'une prise est de 5 s, ratio 9:16, `audio_mode=silent`, prompt inspiré du plan produit **validé** de la première publicité, `seed=812310`. La source est recadrée à 768×1344 en PNG avant tout calcul. Le workflow n'altère aucun Studio historique, aucun DNS, aucune branche `main`, et ne déploie pas une nouvelle application.

**Limite :** la publication GitHub du code n'est pas une vidéo livrée. Le MP4 n'existera qu'une fois le run GitHub Actions passé et son artifact téléchargé.