# Exécution GPU à la demande

## Principe

Aucun GPU au repos. L'application ne provisionne rien : elle exécute des commandes
sur une machine GPU dont les chemins sont fournis par l'environnement. Rendre un
pod actif ou non est une décision humaine (ou du script de démarrage que vous
ajouterez), pas une propriété cachée du studio.

## Fournisseurs comparés (prix publics, octobre 2026)

| GPU | RunPod Community | RunPod Secure | Vast.ai (marché) | Modal | Remarque |
|---|---|---|---|---|---|
| RTX 4090 24 Go | ~0,34 $/h | ~0,69 $/h | 0,13–0,50 $/h | — | suffisant pour Wan TI2V‑5B |
| RTX 5090 32 Go | ~0,99 $/h | — | — | — | ComfyUI, itérations |
| A100 80 Go | ~1,19 $/h | ~1,39 $/h | 0,50–0,80 $/h | ~2,50 $/h | LongCat 720p, LTX fp8 + offload |
| H100 80 Go | ~1,99 $/h | ~2,89 $/h | 1,50–2,30 $/h | ~3,95 $/h | LTX DFR 1080p confortable |
| B200 | — | ~3,99 $/h+ | — | ~7 $/h+ | FlashAttention 4 obligatoire |

**Choix par défaut : RunPod Secure pour la production, Vast.ai pour les
itérations exploratoires.**

Pourquoi pas le moins cher : sur Vast.ai, un hôte qui redémarre au milieu d'une
génération de 3 minutes fait perdre plus d'argent (et surtout de temps) que la
différence horaire. RunPod Secure facture à la seconde, offre un vrai stockage
réseau et une image maintenue ; c'est ce qui compte quand une vidéo doit sortir.

Pourquoi pas Modal en production : facturation à la seconde et démarrage à froid
très court, mais ~35 % plus cher à l'heure pour la même carte, et l'upload de
66 Go de poids à chaque nouvelle machine est un piège classique.

## Dimensionnement par tâche

| Tâche | GPU minimum | Recommandé | Commentaire |
|---|---|---|---|
| Voix (Chatterbox 500M) | CPU | T4 / 4090 | CPU suffisant, quelques secondes par phrase |
| Voix (VoxCPM2 2B) | T4 16 Go | 4090 | RTF ~0,30 sur 4090 |
| Avatar LongCat 1.5 (720p, int8) | A100 40 Go | A100 80 Go | 2 GPU pour la vitesse (context parallel) |
| LTX-2.5 distilled 1080p | 24 Go (fp8) | 4090/5090 pour itérer | brouillon avant DFR |
| LTX-2.5 DFR 1080×1920 | A100 80 Go (fp8 + offload) | H100 80 Go | la qualité production |
| Montage / QC | CPU | CPU | aucun GPU |

Le montage tourne **localement** : on ne paie pas un pod GPU pour exécuter ffmpeg.

## Recettes

```bash
# machine GPU neuve (Ubuntu 22.04, CUDA 12.8)
bash scripts/gpu/setup_ltx.sh        # clone LTX-2, uv sync, télécharge ~66 GiB
bash scripts/gpu/setup_avatar.sh     # clone LongCat-Video, poids 1.5
bash scripts/gpu/setup_tts.sh        # venv chatterbox + voxcpm
```

Puis, côté studio (sur la VM légère) :

```bash
export PVS_LTX_PYTHON=/opt/LTX-2/.venv/bin/python
export PVS_LTX_REPO=/opt/LTX-2
export PVS_LTX_MODELS=/models/ltx-2.5
export PVS_AVATAR_REPO=/opt/LongCat-Video
export PVS_AVATAR_WEIGHTS=/models/LongCat-Video-Avatar-1.5
export PVS_TTS_PYTHON=/opt/tts-venv/bin/python
export PVS_PROVIDER=runpod
```

## Deux topologies possibles

**A. Tout sur le pod** (le plus simple, recommandé pour démarrer)
Le studio (API + UI) tourne sur le pod GPU. L'utilisateur ouvre l'URL ; le pod
est arrêté quand la session de production est terminée. Aucun réseau privé à
configurer. C'est ce que permettent les scripts actuels.

**B. Studio local, rendu distant**
Le studio tourne sur une petite VM ; les moteurs tournent sur un pod joignable
(SSH, ou ComfyUI via HTTP avec `PVS_COMFY_URL`). Plus de confort pour plusieurs
producteurs, mais il faut exposer un chemin : SSH tunnel ou `PVS_COMFY_URL`
protégé. Les adaptateurs `subprocess` exigent alors un wrapper SSH documenté —
non fourni ici, car non testé.

## Volumes et reprise

- Les poids (66 GiB pour LTX-2.5, plusieurs dizaines de Go pour LongCat) doivent
  vivre sur un **volume réseau persistant**. Les retélécharger à chaque pod coûte
  plus que le GPU économisé.
- Les sorties sont écrites dans `data/projects/<id>/jobs/<job>/` : monter `data/`
  sur le même volume suffit à survivre à la destruction du pod.
- Au redémarrage, `PVS_REQUEUE_ON_BOOT=1` remet en file les jobs interrompus.
  Les jobs déjà terminés ne sont jamais rejoués.
- Un job annulé termine son sous-processus (`terminate`) : pas de GPU zombie.

## Contrôle des coûts

Chaque job enregistre ses secondes GPU et le tarif appliqué. Les échecs sont
facturés dans `cost_events` (un essai raté a réellement consommé du GPU).

Règles de conduite proposées :

1. **Toujours** générer en `distilled` d'abord ; ne passer en DFR qu'un cadrage validé.
2. Un plan avatar se génère **après** validation de la voix (le TTS est 10× moins cher).
3. `Retake` plutôt que régénération complète dès qu'un seul passage est mauvais.
4. Arrêter le pod dès l'export terminé : `PVS_MAX_WORKERS=1` garantit qu'aucun job
   ne tourne en arrière-plan sans que vous le sachiez — `/api/jobs` reste la
   source de vérité.
5. Suivre `cost_per_export_usd` et `attempts_per_success` (page *Moteurs & coûts*),
   pas la durée du pod.

## Ce qui n'est pas automatisé (volontairement)

Le démarrage et l'arrêt du pod. Un orchestrateur de pods (création automatique à
la demande, arrêt sur inactivité, gestion des quotas) est une infrastructure
réelle : elle ne se justifie qu'après la preuve de qualité. Tant que la production
est de l'ordre de quelques vidéos par semaine, un pod lancé à la main est moins
cher et beaucoup plus simple.
