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

## Exécution réelle du premier plan : TEST REFUSÉ

- Action GitHub [run #39964158427](https://github.com/saillardsimon71-del/nouveau-studio/actions/runs/39964158427) : **succès technique, échec visuel**.
- Vidéo : 5,042 secondes, 768×1344, 24 fps natifs, LTX-2.5 Distilled, L40S, image-guided strength 0.85.
- Génération : 109,194 secondes GPU, **estimation Modal : 0,0861 USD** ; vérifier la facture dans Modal.
- L'image Pexels choisie pour cette première expérience avait **une véritable étiquette imprimée** ; elle n'était donc pas le bon input pour une création de parfum fictive sans marque.
- Revue visuelle de frames toutes les 0,5 s : le flacon se transforme d'un petit flacon étiqueté en bouteille carrée sans étiquette entre 1 et 3 secondes. Des objets et le décor d'arrière-plan s'effacent. La géométrie du produit et la continuité ne sont PAS maintenues ; le plan ne ressemble pas à une publicité premium.
- **DÉCISION : ne pas utiliser le clip, ne pas lancer les plans 2 et 3.**

## Marche à suivre corrigée : aucune autre dépense automatique

Le workflow a été rendu **manuel uniquement**. Avant un éventuel second essai, il faut ajouter au dépôt un fichier PNG `assets/sitequivend/produit-reference.png` représentant **un produit fictif ou explicitement autorisé, propre, sans inscription de marque et en qualité publicitaire**, de préférence l'image originale déjà utilisée par la première publicité. L'image étant un facteur de qualité majeur, on doit l'examiner avant de relancer l'action.

Le workflow exige une validation manuelle `confirm_spend: oui`, refuse l'absence du PNG **avant GPU**, et réutilise le worker Modal existant. Aucun rerun, aucune variation ni aucun autre rendu ne doit être lancé sans décision explicite.

### Rappels pour la suite

- Le scénario complet reste prévu à 12–14 s en 3 plans, MAIS il n'est **pas réalisé**.
- Le fichier du premier essai rejeté est disponible dans les GitHub Actions Artifacts du run #39964158427.
- Le rendu final à 48 fps minimum n'est pas encore produit ; l'indicateur 24 fps du MP4 est celui de la génération native LTX, pas un export final.
- On ne peut pas remplacer la validation du visuel de référence par des promesses de « qualité cinéma » dans le prompt.
