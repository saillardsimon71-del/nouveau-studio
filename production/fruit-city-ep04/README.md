# Fruit City — Episode 04 : L'autre Durio

## Premier lancement vérifié — 29 octobre 2026

- Run GitHub Actions : https://github.com/saillardsimon71-del/nouveau-studio/actions/runs/40846790352
- Résultat : storyboard 13 plans/65 s **validé** ; démarrage GPU **bloqué avant toute génération**.
- Cause démontrée par les logs : le secret Modal présent dans **ce dépôt** authentifie encore le workspace `kulejean567`. La cible de production choisie est `lucj76861`.
- Le changement des secrets effectué précédemment dans **UGCv2** ne les modifie pas dans `nouveau-studio` : chaque dépôt possède ses propres secrets.
- Action requise : mettre à jour `MODAL_TOKEN_ID` et `MODAL_TOKEN_SECRET` sous `nouveau-studio → Settings → Secrets and variables → Actions` avec un token du workspace `lucj76861`, puis utiliser **Re-run all jobs** sur le run ci-dessus.
- Le volume `studio-ltx25-models` et ses cinq fichiers ne seront contrôlés qu'après identification du bon compte. Aucun GPU n'a été lancé pendant ce premier run.


**Format :** TikTok/Reels/Shorts 9:16 • **durée :** 65 s (13 × 5 s) • **langue :** français • **diffusion :** aucune publication automatique.

## Vérification de la création des images

Le pipeline utilisé dans l'épisode 3 ne crée pas d'images-clés en amont. Il appelle directement `deploy/modal_ltx_worker.py` en **text-to-video** : 11 plans de 5 s ont déjà été générés avec succès dans GitHub Actions (run 40119365074). La documentation de production précise que certaines images préparatoires des publicités ont été faites avec ImageGen **hors** des scripts. Le worker LTX prend une image PNG en option (`--image-png`) pour de l'image-to-video, mais il ne possède pas un générateur d'images indépendant.

Aucune véritable image de référence de Durio/Momo n'étant versionnée ici, cet épisode reproduit le parcours éprouvé (prompts visuels textuels détaillés → vidéo LTX réelle → voix en postproduction → montage). **La cohérence des personnages n'est pas garantie.** Toute publication exige un visionnage humain.

## Histoire

- **0–5 s :** une voix dit à Durio « t'es pas le vrai » et sa chaîne s'anime toute seule.
- **5–20 s :** Durio défie la grille ; la voix impose une règle ; Momo entre en panique.
- **20–35 s :** Durio accuse Momo, qui avoue avoir ouvert la grille.
- **35–50 s :** l'ombre révèle connaître Momo, et la chaîne de Durio commence à luire.
- **50–65 s :** la voix révèle que Durio est la clé, sa chaîne est attirée vers la grille, la cellule s'ouvre : « Trop tard... je suis dehors. »

## Technique

- Script : `scripts/production/fruit_city_ep04.py`
- Action : `.github/workflows/fruit-city-ep04.yml`
- Job : vérification JSON storyboard, secrets, compte Modal `lucj76861`, volume `studio-ltx25-models` et 5 poids **avant** utilisation du GPU L40S.
- Moteur : LTX-2.5 via worker existant, 13 appels séquentiels, pas de mock, pas de retry GPU.
- Audio : voix françaises Edge TTS avec fallback déclaré, bruitages synthétiques, sous-titres SRT et incrustés, mastering.
- Sorties : MP4 1080×1920/24fps, miniature, SRT, storyboard, rapport de provenance, clips sources et métadonnées de coût estimé.
- Déclenchement unique : push d'un `TRIGGER_RENDER.txt` contenant exactement `APPROVED_GPU_RENDER_EP04_20261029` avec le message de commit `RUN_FRUIT_CITY_EP04_ONCE_20261029`.
- En cas de mauvais compte, secrets manquants ou poids absents : **échec sans GPU**. Les identifiants GitHub de l'ancien compte ne sont jamais remplacés automatiquement.
- Le résultat **n'est pas** publié sur TikTok.

## Contrôles avant publication

Vérifier les 13 personnages, les lunettes de Momo, la chaîne de Durio, la continuité cellule/grille, le débit des voix, les sous-titres, les artefacts visuels, et le timing réel de 65 secondes. Les métriques générées par le pipeline ne prouvent pas la qualité éditoriale.
