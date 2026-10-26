# Portfolio ÉCLAT 02 et PULSE 01

Production dédiée, sans modification du Studio, du site ou du worker déployé.
Référence récupérée : MAISON 01, Actions 40188342628, 20,667 s.
Même H3 FL2VA INT8, encodeur Qwen NVFP4, L40S, 20 étapes,
res_multistep/simple, 24 i/s, 768x1344 natif. Export recadré 9:16.

## Storyboards

ÉCLAT 02, 15,5 s : macro pipette et verre ambré, geste sérum sur la joue,
packshot du flacon générique à étiquette blanche, signature sur fond ivoire.
Trois plans animés, fondus de 6 images, lumière crème et champagne.
Un seul visage, un seul packshot, aucune marque ajoutée dans les images.
Musique : Reverie, Scott Buckley, piano et nappes.

PULSE 01, 13,25 s : concentration en tenue technique, poussée sur haltères,
insert matière de 1 s, retour au calme déterminé, signature sur fond charbon
et accent citron. Trois générations donnent quatre plans montés du même
shooting cottonbro, avec la même athlète et la même salle.
Coupes franches, lumière de fenêtre contrastée, ombres froides.
Musique : Catalyst, Scott Buckley, pulsation synthétique et orchestre.

Les sources, auteurs, recadrages, prompts et seeds sont dans le script et
dans sources.json généré avec empreintes SHA-256. Photos authentiques,
sans génération d'images fixes. Crédits Pexels et CC BY 4.0 conservés.
La validation des licences a été exclue du périmètre par instruction explicite
de l'utilisateur le 26 octobre 2026 ; elle n'est pas déclarée acquise.

## Exécution et contrôles

1. Préparation CPU : téléchargement réel, décodage, résolution des recadrages,
   empreintes, musique et test du contrat H3, doctor du worker existant.
2. Inspection des six images préparées avant le lancement GPU.
3. Deux lots de trois plans, sans redéploiement, sans relance automatique.
4. Montage 1080x1920 et web 720x1280, H.264/AAC faststart.
5. Inspection visuelle des MP4, contrôle des mains, peau, objets, mouvements,
   raccords, durée et audio. Musique instrumentale et bruitages originaux ;
   la piste sonore H3 est écartée pour ne pas intégrer de voix imprévue.
6. Livraison des fichiers et du rapport factuel dans une PR non fusionnée.

Les vidéos de prospection ne sont pas utilisées. Aucun nouveau moteur,
aucun agent, aucune voix, aucun merge ou changement de production.
