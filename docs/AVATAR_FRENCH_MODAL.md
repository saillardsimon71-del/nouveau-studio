# Avatar français — pilote LongCat sur Modal

## Etat réellement prouvé
- LTX-2.5 text-to-video (3 s) : MP4 réel validé sur Modal.
- LTX-2.5 image-to-video (5 s) : MP4 réel disponible via GitHub Actions #39829988746 ; fidélité du visage à vérifier visuellement.
- LongCat-Video-Avatar-1.5 : un ancien MP4 réel de 3,72 s est archivé dans le [run 39839348041](https://github.com/saillardsimon71-del/nouveau-studio/actions/runs/39839348041). La qualité du jeu n'est pas démontrée. L'état du parcours voix validée et de la continuation figure dans [HUMAN_PERFORMANCE.md](HUMAN_PERFORMANCE.md).

## Isolation des ressources
- Workspace existant : `kulejean567`.
- Nouvelle application : `pvs-longcat-avatar`.
- Nouveau volume : `pvs-longcat-models`.
- **Ne touche pas** `studio-ia-ltx`, `studio-ltx25-models`, `fasth3-models`, `voxcpm-models`.
- Premier rendu avatar sur A100 80GB, modèles INT8, 8 pas distillés, 480p recadré en vertical 9:16.

## Workflow GitHub
`.github/workflows/modal-avatar.yml` : `voice`, `prepare`, `doctor`, `render`.
Secrets existants : `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`.

1. `voice` : génère une courte voix française synthétique (fr-FR-HenriNeural), archive MP3 + WAV (CPU, 0 GPU).
2. `prepare` : télécharge **une fois** les composants LongCat nécessaires dans le nouveau volume Modal (CPU, 0 GPU ; stockage et CPU potentiellement facturés).
3. `doctor` : vérifie les huit sections de poids par leur présence sans lancer de GPU.
4. `render` : fabrique sa voix française puis génère avec le portrait synthétique `benchmark_assets/character_reference.png`, exige `confirm_spend: oui` et archive MP4 + métadonnées. Un run incomplet doit échouer, **jamais produire une simulation présentée comme réelle**.

Le `push` du workflow sur `main` n'exécute que `voice`, puis ce déclencheur sera retiré. `prepare` et `render` sont des commandes distinctes : pas de nouveau téléchargement à chaque tentative de rendu. Le téléchargement des composants nécessaires peut être volumineux ; l'amorçage CPU évite de gaspiller le GPU.

## Limitations à mesurer
- Le modèle officiel LongCat privilégie un cadrage paysage. Le pilote recadre le MP4 en 9:16 au montage, avec risque de perdre une partie du cadre.
- Le script officiel génère d'abord un segment de 93 frames à 25 fps, soit environ 3,72 s. C'est un test de lèvres, pas encore un présentateur de 60 s.
- Voix synthétique neutre de démonstration. Pour une voix propriétaire récurrente, brancher le moteur TTS choisi après validation du lip-sync.
- Ne pas chiffrer « coût par vidéo acceptée » avant visionnage humain.
- Les échecs de compilation FlashAttention, de téléchargement et d'inférence doivent être corrigés à partir des logs Modal, sans refaire le moteur LTX déjà fonctionnel.

## Premier débouché commercial, sans fausses preuves
Mettre en scène une vraie automatisation démontrable : réception d'une facture **fictive clairement identifiée**, extraction, ajout dans un tableur de démonstration et contrôle humain avant envoi. Pour le média, afficher le flux réellement exécuté, pas une interface fictive qui prétend avoir fait le travail. Exemple de CTA : « Vous voulez automatiser ce traitement chez vous ? Écrivez FACTURE. » Offre pilote d'installation 149–299 €, montant à ajuster selon le besoin et le travail réellement réalisé. Aucun revenu ou résultat client ne doit être inventé.
