# MiniMax H3 sur nos GPU Modal — nouveau-studio

## Objectif

Moteur **modal_h3** dans le pipeline ordinaire `video`, préféré à `modal_ltx` uniquement lorsqu'une vraie fonction Modal H3 est accessible.

- `pvs-minimax-h3` : application GPU H3 **distincte**.
- `pvs-minimax-h3-models` : volume persistant H3 **distinct**.
- `pvs-ltx` : ancien moteur inchangé, conservé comme repli.
- **Aucune API MiniMax facturée à la vidéo**, GPU Modal uniquement pour la génération.
- Photos utilisées comme référence : photographies réelles Pexels ou assets client, transformées en PNG dans le pipeline actuel.

## Architecture & modèles

Implémentation : `deploy/modal_h3_worker.py`, ComfyUI natif et `MiniMaxH3ImageToVideo`.
Les quatre fichiers du dépôt Hugging Face `Comfy-Org/MiniMax-H3` sont
téléchargés via `hf_hub_download` sur un volume Modal persistant, sans copier
le dépôt original de centaines de Go.

| Rôle | Fichier |
|--|--|
| FL2VA diffusion, INT8 pruned | `diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| Qwen3-VL, NVFP4 | `text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| Video VAE | `vae/minimax_h3_video_vae_int8_convrot.safetensors` |
| Audio VAE | `vae/minimax_h3_audio_vae_fp32.safetensors` |

Ces quatre poids totalisent ~37,3 Go (sans LoRA turbo). Le stockage, CPU et
RAM Modal sont aussi facturables : il n'y a pas uniquement le prix du GPU.
La qualité vidéo native se juge à 24 i/s, environ 768 px sur la petite
dimension, 4 à 15 s par plan ; l'interpolation/upscale n'est pas une qualité native.

La configuration initiale cible L40S avec offload ComfyUI `--lowvram`,
8 CPU et 64 GiB RAM. Cette configuration **n'est pas encore prouvée par un rendu**.
Ne pas annoncer le coût/minute ou l'absence de déformation avant un benchmark.

## Provisionnement via GitHub Actions

`.github/workflows/modal-h3-local.yml` :
- Push ordinaire : validation syntaxique gratuite.
- Push de commit `H3_STAGE_MODELS_ON_MODAL_20261025` sur la branche
  `feat/modal-h3-engine-20261025` : télécharge les poids sur CPU Modal
  dans le volume dédié (environ 37 GB), à exécuter **une fois**.
- Push de commit `H3_DEPLOY_WORKER_ON_MODAL_20261025` sur cette même
  branche : `modal deploy deploy/modal_h3_worker.py`, après vérification
  que les poids sont entièrement présents.
- Bouton de workflow dispatch sur la branche principale, après fusion :
  `doctor`, `prepare`, `deploy`, avec confirmation de dépense pour les deux derniers.

Les secrets `MODAL_TOKEN_ID` et `MODAL_TOKEN_SECRET` existants sont réutilisés.
Les poids H3 ne sont jamais mélangés aux modèles LTX.

## Contrat du pipeline

Comme LTX :
```python
engine = get("modal_h3")
# request.inputs["reference_image"] pointe vers un JPEG/PNG réel
# request.prompt, request.duration_s, request.project["format"] sont inchangés
```

Le composant `ModalH3Engine` appelle
`modal.Function.from_name("pvs-minimax-h3", "render_clip")`.
Le worker accepte `prompt`, `duration_s` (4..15 s), `aspect_ratio`,
`seed`, `image_png_base64`, `steps`; renvoie MP4 en Base64 + métadonnées.
Les mêmes jobs du Studio récupèrent et montent la sortie.
H3 est prioritaire uniquement si `PVS_MODAL_ENABLED=1` et que Modal
permet de charger la fonction. Sinon LTX reste prioritaire ; le fallback
doit rester visible dans le journal des jobs.

## Contrôle qualité avant bascule finale

1. `doctor` doit confirmer 4 poids présents et leur taille.
2. `modal deploy` doit passer.
3. Générer **un seul plan** I2V de 4-5 s avec photo Pexels réelle
   et vérifier son MP4 et l'audio.
4. Vérifier visuellement les mains, jambes, yeux, tissus et morphing à
   chaque seconde : les déformations de MOVE interdisent une publication sans QC.
5. Seulement après, sélectionner H3 par défaut dans le studio pour les nouveaux plans.

## Notes de droits (indépendantes de la technique)

La licence officielle des poids MiniMax H3 contient actuellement des limites
territoriales et des conditions commerciales. Le fait que l'installation soit
techniquement possible ne valide pas un usage autorisé ; les termes applicables
doivent être vérifiés séparément.
