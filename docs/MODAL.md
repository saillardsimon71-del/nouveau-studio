# Branchement du compte Modal de Studio IA V2

Objectif : produire de vrais MP4 GPU (LTX-2.5, puis avatar français) avec le
compte Modal qui a déjà servi à Studio IA V2, **sans reconstruire le studio** et
**sans rien redéployer par-dessus l'ancien projet**.

Chemin d'exécution : téléphone → GitHub Actions → Modal → GPU → artifact MP4.
L'Arena n'a ni route réseau vers `api.modal.com` ni jeton Modal : tout passe par
le workflow, jamais par une commande locale.

---

## A. Compte Modal : ce qui est établi, ce qui reste à confirmer

Le dépôt `saillardsimon71-del/StudioIA` documente **deux** comptes, et le même nom
d'application est utilisé dans les deux :

| Élément | Ancien compte | Compte de migration |
| --- | --- | --- |
| Source | `docs/studio/LTX.md` | `studio-v2/deploy/MIGRATION_LTX_MODAL.md` |
| Nom cité | `falconapp-cloud` | `kulejean567` |
| Date | historique (V1) | 2026-10-20, commit `48f6f16` |
| App | `studio-ia-ltx` | `studio-ia-ltx` (identique) |
| GPU | `RTX-PRO-6000` (`deploy/modal_ltx.py`) | `L40S`, 8 CPU, 64 GiB (`modal_ltx_v2.py`) |

Conséquences, et c'est le point important :

- **Le nom d'app ne prouve pas le compte.** `studio-ia-ltx` existe des deux
  côtés. On ne déduit donc *jamais* le workspace d'un `app list`.
- **Le nom de workspace n'est pas vérifiable depuis le dépôt.** Le seul document
  qui nomme `kulejean567` est une note de migration, et il dit explicitement que
  l'Arena n'a pas accès à ce compte. On ne le prend pas pour argent comptant.
- **La seule preuve acceptable** est lue sur le jeton, à l'exécution :
  `modal token info` (workspace), puis `modal volume ls studio-ltx25-models`
  (le volume n'existe que là où Studio IA V2 a écrit) et enfin le rapport
  `doctor()` (les 5 poids réellement présents).
- **Le solde de crédits n'est pas exposé par l'API publique Modal** dans ce que
  ce dépôt utilise. Il se vérifie dans le dashboard (Settings ▸ Billing). Le
  workflow ne prétendra jamais avoir « vérifié le solde » : il prouve l'identité
  du workspace et la présence des modèles, rien de plus.

Le workflow échoue volontairement si la variable de dépôt `MODAL_WORKSPACE_EXPECTED`
est définie et différente du workspace du jeton, et si le volume
`studio-ltx25-models` est absent du compte.

## B. Ce qui est réutilisé, et à quelles conditions

Réutilisé **en lecture seule**, sans écriture ni suppression :

| Ressource | Réutilisation | Vérification |
| --- | --- | --- |
| Volume `studio-ltx25-models` | monté à `/mnt/ltx-models`, `with_mount_options(read_only=True)` | `doctor()` liste les 5 fichiers et leur taille |
| 5 poids LTX-2.5 (INT8 convrot ComfyUI) | symlinks dans `/opt/ComfyUI/models/*` | nom exact + présence obligatoire, sinon `RuntimeError` |
| Recette ComfyUI deux passes | graphe reconstruit, mêmes nœuds, mêmes sigma | test `test_two_pass_graph_uses_pinned_weights_and_upsampler` |
| Révisions épinglées | LTX-2.5 `49b093a…`, ComfyUI `d49e888…`, torch 2.8.0 cu128 | constantes en tête de `deploy/modal_ltx_worker.py` |
| App `studio-ia-ltx` | **jamais** redéployée, jamais arrêtée | le workflow refuse le nom et déploie `pvs-ltx` |

Pourquoi ComfyUI et pas `ltx_pipelines` : les poids du volume sont les variantes
**ComfyUI INT8-convrot**, pas les safetensors bf16 attendus par le CLI natif. Le
chemin ComfyUI est celui qui a réellement rendu des clips dans Studio IA V2
(78 s à chaud, 151-197 s à froid pour 145 frames en 768×1344 sur L40S). Le CLI
natif reste une option ultérieure : il exige son propre volume et ~66 GiB de
téléchargement.

Non réutilisé, et pourquoi :

- `fasth3-models` (H3) et `voxcpm-models` (TTS) : volumes distincts, apps
  distinctes. Ils ne servent pas au premier rendu LTX. Aucune écriture dessus.
- Le Dict de progression `studio-ia-ltx-progress` : propre à l'ancienne app, on
  ne le touche pas ; le suivi se fait par les artifacts et les logs GitHub.

Points ouverts (à trancher par les logs du premier run, pas par supposition) :

1. Le volume `studio-ltx25-models` est-il bien dans le compte du jeton ? → étape
   *preflight*.
2. Les 5 fichiers y sont-ils complets (pas de téléchargement interrompu) ? →
   `doctor()`.
3. Les nœuds ComfyUI `LTXVImgToVideoInplace` / `LTXVAudioVAEDecode` existent-ils
   dans la révision `d49e888…` telle qu'installée ? → le premier rendu le dit ; en
   cas d'échec, le message d'erreur ComfyUI est remonté tel quel.
4. LongCat-Avatar (Test B) n'a **aucun** volume existant : il faudra un volume
   neuf et un téléchargement. C'est un second déploiement, pas une modification
   de l'existant.

## C. Ce que ce dépôt ajoute

```
deploy/modal_ltx_worker.py      app `pvs-ltx` : doctor() 0 GPU, render_clip() L40S,
                                et l'entrée locale `--mode doctor|render` appelée par la CI
scripts/check_benchmark_assets.py   validation PNG + WAV avant dépense
benchmark_assets/               inputs réels des tests (image fournie, voix à fournir)
.github/workflows/modal-ltx.yml  preflight → doctor → deploy → render → artifact
docs/MODAL.md                   ce document
```

Rien d'autre n'est modifié : ni l'UI, ni les moteurs, ni le schéma. L'API du
studio reste inchangée ; brancher `render_clip` sur l'adaptateur `ltx_native.py`
viendra après la première preuve de rendu.

Garde-fous intégrés :

- `scaledown_window=2` s sur `render_clip`, `min_containers=0` : le GPU s'éteint
  seul dès la fin de la requête.
- `max_containers=1` : un seul GPU à la fois, pas de fan-out accidentel.
- `confirm_spend: "oui"` obligatoire pour `deploy`, `render` et `full` : aucune
  dépense sur un run `preflight`/`doctor`.
- Aucun secret dans le dépôt : les deux secrets GitHub sont lus par variable
  d'environnement, et le log n'affiche qu'une empreinte masquée du jeton.
- Le MP4 est vérifié par `ffprobe` avant d'être renvoyé : un fichier illisible
  fait échouer le run au lieu de produire un artifact trompeur.

## D. État de préparation

| Élément | État | Preuve / ce qu'il faut |
| --- | --- | --- |
| Contrat de requête (`validate`) | **testé** | 32 tests locaux (54 avec la suite complète), sans GPU |
| Graphe ComfyUI deux passes | **testé** (structure) | nœuds, poids, upsampler, mode image, mode silencieux |
| Entrée CI → MP4 + métadonnées | **testé** (avec un faux `render_clip`) | `test_render_entrypoint_writes_the_mp4_and_metadata` |
| Validateur d'inputs | **testé** | refuse PNG non vertical, WAV absent/silencieux |
| Identité du workspace Modal | **non testé** | nécessite les 2 secrets GitHub + 1 run `preflight` |
| Présence des poids | **non testé** | nécessite `doctor` sur le compte |
| Rendu LTX réel | **non testé** | nécessite `deploy` puis `render` |
| Avatar français LongCat | **non commencé** | volume neuf + voix ; hors du premier rendu |

Rien de ce qui précède n'a consommé de crédit : aucun appel Modal n'a été émis
depuis cette session (le sandbox n'a pas de route vers `api.modal.com`).

## E. Actions iPhone minimales

1. **Ajouter les deux secrets** (obligatoire, une seule fois) :
   `github.com/saillardsimon71-del/nouveau-studio` → **Settings** → **Secrets and
   variables** → **Actions** → **New repository secret** :
   - `MODAL_TOKEN_ID`
   - `MODAL_TOKEN_SECRET`
   Les valeurs viennent du dashboard Modal (Settings ▸ API Tokens ▸ *New token*,
   portée « workspace »). Ne les envoyez jamais dans le chat.
2. **(Recommandé) Épingler le workspace** : même écran, onglet **Variables** →
   `MODAL_WORKSPACE_EXPECTED` = le nom affiché en haut du dashboard Modal. Le
   workflow refusera alors de tourner sur un autre compte.
3. **(Optionnel) Choisir le GPU** : variable `MODAL_GPU` (`L40S` par défaut,
   `RTX-PRO-6000` est le moins cher du projet historique).
4. **Fournir la voix** : `benchmark_assets/voice_reference_fr.wav`, procédure
   détaillée dans `benchmark_assets/README.md` (Dictaphone → Fichiers → upload
   GitHub). Non bloquant pour le Test A cinématique.
5. **Lancer le run** : onglet **Actions** → **Modal LTX-2.5** → **Run workflow**
   → `stage: preflight`, `confirm_spend: non` → **Run**. Choisir la branche
   `arena/d40d9dd5-nouveau-studio` dans la liste des branches du bouton *Run
   workflow* : le fichier de workflow doit exister sur la branche lancée.
   Aucun GPU n'est utilisé.

Le premier `preflight` affiche le workspace réel, les apps et les volumes du
compte, puis le contenu du volume LTX. C'est ce log qui confirme — ou infirme —
que le compte est bien celui de Studio IA V2.

## F. Première génération réelle

Après un `preflight` vert :

1. `stage: deploy`, `confirm_spend: oui` → déploie `pvs-ltx` (jamais `studio-ia-ltx`).
2. `stage: doctor`, `confirm_spend: non` → prouve le montage des 5 poids.
3. `stage: render`, `confirm_spend: oui`, `duration: 3`, `aspect: 9:16`,
   `audio_mode: native`, prompt court : première prise **réelle**, ~1 min de GPU
   facturée, MP4 téléchargeable dans **Artifacts**. Le rendu tourne dans un run
   éphémère (`modal run`), qui se termine avec le job : rien ne reste allumé.
4. Si le MP4 se lit : `stage: render`, `duration: 5`, prompt du Test A, puis
   `reference_image: benchmark_assets/character_reference.png` pour un plan ancré.

Coût à mesurer et à consigner à chaque run (le workflow l'écrit dans le résumé) :
secondes GPU totales, démarrage ComfyUI, rendu, $ estimés, coût par prise
acceptée, coût par vidéo utilisable.

Pour tout couper immédiatement : `stage: stop` dans le workflow (bouton **Run
workflow**, aucun GPU), ou `modal app stop pvs-ltx` depuis le dashboard.
`scaledown_window=2` éteint déjà le conteneur après la dernière requête, et un
run `render` éphémère s'arrête de lui-même à la fin du job.
