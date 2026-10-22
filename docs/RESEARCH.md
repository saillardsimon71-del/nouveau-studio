# Sélection technique — état des technologies, octobre 2026

Ce document est une décision, pas un catalogue. Chaque ligne a été vérifiée sur
le dépôt ou la documentation officielle à la date de rédaction ; les chiffres de
vitesse qui viennent des auteurs sont marqués comme tels et restent à confirmer
par nos propres mesures (voir `BENCHMARKS.md`).

## 0. Contraintes réelles qui décident de tout

| Contrainte | Valeur | Conséquence architecturale |
|---|---|---|
| Machine utilisateur | pas de GPU exploitable pour du 22B | tout le rendu est distant, abandonné/relancé à la demande |
| Budget | pas de GPU au repos | pas de pod permanent, pas de file distribuée, pas de serveur d'inférence inactif |
| Objectif | 5 vidéos excellentes/semaine | optimiser le **coût par vidéo acceptée**, pas le débit |
| Format | vertical 9:16, 20–60 s | clips de 3–12 s assemblés, pas un plan unique de 35 s |
| Langue | français parlé | la voix n'est pas un détail : c'est la moitié du rendu |

## 1. Décision en une page

| Fonction | Retenu | Rôle | Rejeté / écarté | Pourquoi |
|---|---|---|---|---|
| Vidéo (B-roll, plans ciné) | **LTX-2.5** via `ltx_pipelines` natif | moteur vidéo principal, image→vidéo et texte→vidéo, avec audio natif | Wan2.2 (reste en comparaison), Sora/Veo (API fermée, non intégrée ici) | 22B, sortie 1024×1536@24fps, **DFR** pour la qualité production, **Retake** pour la régénération ciblée, `--image` pour la cohérence d'identité |
| Avatar parlant | **LongCat-Video-Avatar 1.5** | présentateur récurrent qui parle | InfiniteTalk (comparaison), Wan2.2-S2V | Whisper-large pour le lip-sync, distillation 8 pas, INT8, continuation vidéo (plan long) |
| Voix FR | **Chatterbox Multilingual V3** (défaut) + **VoxCPM2** (qualité) | voix clonée, émotion, 48 kHz | IndexTTS-2.5, Orpheus, Dia, Kokoro | IndexTTS ne couvre pas le français ; Kokoro n'a pas de clonage ; Orpheus/Dia sont anglais |
| Images / références | **Qwen-Image** (+ Qwen-Image-Edit) | génération et édition des images de référence et des premières frames | Flux/SDXL | édition précise, rendu de texte correct, disponible localement |
| Orchestration | **notre API** + adaptateurs | 1 contrat `Engine`, 1 runner de jobs | ComfyUI comme socle, framework d'agents | ComfyUI = backend *optionnel* ; un graphe n'est pas une architecture produit |
| Montage | **ffmpeg** | assemblage, sous-titres ASS, mixage, loudness | MoviePy, Remotion | déterministe, rapide, sans GPU, lisible et scriptable |
| Direction créative | **un seul LLM** (DeepSeek par défaut), sortie JSON validée | brief → storyboard | multi-agents | un prompt + un schéma + un retry couvre 100 % du besoin |
| Calcul | **GPU à la demande** (RunPod/Vast/Modal) | exécution | pod permanent | coût au repos nul, fournisseur interchangeable |

## 2. LTX Desktop — la question posée, tranchée

**Ce que c'est.** Application Electron + Python (Node/pnpm + `uv`), Apache-2.0,
bêta, développée pour tourner **en local sur un GPU NVIDIA ≥ 24 Go (32 recommandé)**
ou Apple Silicon ≥ 48 Go. 100–160 Go de disque pour les poids et LoRA.

**Ce qu'elle fait déjà très bien :** file de génération partagée, bibliothèque
d'assets persistante, Retake (régénération d'une zone), Extend, outils IC-LoRA
(day→night, deblur, colorisation, clean plate), recettes LoRA (styles, mouvements
de caméra), enrichissement de prompt, assistant, Remote (pilotage depuis un
téléphone via un navigateur sur le même réseau), thème clair/sombre.

**Ce qu'elle ne fait pas :** pas de notion de **projet / storyboard / plan
ordonné avec dialogue**, pas de bibliothèque de **personnages récurrents**, pas de
moteur d'**avatar parlant** ni de TTS, pas de **sous-titres**, pas de **montage
multi-plans** avec musique, pas de suivi de **coût**, pas de **file d'attente
côté serveur pour plusieurs utilisateurs**, et — décisif — elle suppose le GPU
dans la machine.

**Décision : aucune des trois options extrêmes.**

1. ❌ *Construire une interface originale en réutilisant ses composants UI* :
   son frontend est explicitement en refonte (“Frontend architecture is under
   active refactor”, PRs UI refusées) et couplé à un runtime desktop. Coupler
   notre produit à cette base, c'est hériter du refactor.
2. ❌ *Réutiliser l'app telle quelle comme moteur* : il faudrait un GPU local ou
   un Remote exposé, sans API de jobs stable, sans notion de plan, et sans
   isolation par production.
3. ❌ *Construire tout au-dessus de ComfyUI* : ComfyUI est excellent pour
   explorer un modèle, mauvais comme socle produit (graphes fragiles, versions de
   nœuds, pas de sémantique projet/plan/coût).

✅ **Ce que nous réutilisons réellement :** le moteur qui est *sous* LTX Desktop,
c'est-à-dire `ltx_pipelines` (le même code, en CLI). Nous obtenons ses
fonctionnalités — DFR, Retake, Extend, IC-LoRA, recettes caméra — sans hériter de
son IHM ni de son hypothèse « GPU local ». ComfyUI reste branché comme backend
alternatif (`engines/comfyui.py`) pour comparer un même plan entre deux
exécutions. C'est précisément la règle demandée : ne pas reconstruire ce qui
existe, ne pas juxtaposer des dépôts incompatibles, garder une frontière nette.

## 3. Vidéo générative — comparatif

| | **LTX-2.5** | Wan2.2 | Wan2.2-Animate | Helios (Wan2.1) | HuMo |
|---|---|---|---|---|---|
| Taille | 22B (dev + distilled) | A14B MoE, TI2V-5B | 14B | base Wan2.1 | base Wan |
| Résolution / fps | 1024×1536@24, jusqu'à 4K via DFR | 720p@24 (5B), 480/720p (A14B) | 480/720p | 720p, minute-scale | humain-centré |
| Audio natif | **oui** (VAE audio + pipelines A2V) | non (CosyVoice en amont pour S2V) | non | non | audio en entrée |
| Image→vidéo | oui (`--image frame strength`) | oui | animation par vidéo de référence | oui | oui |
| Régénération ciblée | **Retake (`--start-time/--end-time`)** | non | non | non | non |
| Édition vidéo | IC-LoRA, Extend, HDR/EXR | limité | remplacement de personnage | — | — |
| VRAM annoncée | ~24 Go min (Desktop), 66 Go de poids | 80 Go pour A14B 720p, 4090 OK pour 5B | 14B | H100 pour 19.5 fps | — |
| Points faibles | poids lourds, écosystème jeune | pas d'audio natif, pas de retake | détourne le visage | lent | peu outillé |

**Choix : LTX-2.5** pour la production, **Wan2.2 TI2V-5B** conservé comme
comparaison de coût/vitesse sur les plans simples (il tourne sur un 4090 à
0,69 $/h, ce qui change l'économie d'une vidéo de 35 s).

Ce qui fait basculer la décision n'est pas la qualité brute (les deux familles
sont proches sur un plan court) mais **trois fonctions de production** : Retake
(régénérer 2 s au lieu de 8 s), DFR (une passe de détail qui tient en 1080p), et
l'audio natif (utile pour les plans sans dialogue, pas pour l'avatar).

## 4. Avatars parlants — comparatif

| | **LongCat-Video-Avatar 1.5** | InfiniteTalk | Wan2.2-S2V-14B | StableAvatar |
|---|---|---|---|---|
| Encodeur audio | **Whisper-large-v3** | wav2vec2 | audio-driven | — |
| Pas d'inférence | **8 (distillation)** | ~40 + TeaCache | — | — |
| Quantification | **INT8 DiT** | int8 | — | — |
| Durée | segments + continuation vidéo | illimitée (sparse-frame) | 480/720p | — |
| Entrées | texte+audio, image+audio, vidéo+audio | image/vidéo + audio | audio + image | — |
| Multi-personnes | oui (merge / concat) | non | non | non |
| Maturité | 2026, très actif | 2025, très populaire | 2025 | recherche |

**Choix : LongCat-Video-Avatar 1.5**, avec **InfiniteTalk gardé comme fallback
mesuré** (il est excellent en doublage vidéo→vidéo, c'est-à-dire pour rejouer la
voix d'un plan déjà tourné).

Raison : pour un présentateur récurrent, la qualité perçue dépend de trois choses
— synchronisation labiale, stabilité de l'identité sur la longueur, et naturel du
haut du corps. Le passage à Whisper-large et la distillation à 8 pas attaquent
directement les deux premières, et l'INT8 rend le test possible sur un A100 80 Go
sans compromis de durée.

## 5. Voix française — comparatif

| Modèle | Params | Français | Clonage | Expressivité | VRAM | État |
|---|---|---|---|---|---|---|
| **Chatterbox Multilingual V3** | 500M | ✅ (23+ langues) | ✅ ~5 s | `exaggeration`, `cfg_weight` | ~4–6 Go | retenu (défaut) |
| **VoxCPM2** | 2B | ✅ (30 langues, WER FR publié) | ✅ contrôlable | design de voix | ~8 Go | retenu (qualité) |
| IndexTTS-2.5 | — | ❌ (zh/en/ja/es/ar) | ✅ | très bonne | — | écarté : pas de français |
| CosyVoice 3 | 0.5B | ✅ | ✅ | bonne | 8 Go | écarté : pas d'avantage net ici |
| Kokoro 82M | 82M | partiel | ❌ | faible | CPU | écarté : pas de clonage |
| Fish Audio S2 Pro | 4.4B | ✅ | ✅ | très bonne | 12–16 Go | écarté : surdimensionné pour notre débit |

Le français impose de vérifier la couverture linguistique **avant** la qualité
perçue : c'est ce qui élimine IndexTTS malgré d'excellents résultats.

## 6. Modèles écartés volontairement

- **Sora / Veo / Kling API** : excellents, mais fermés, chers au clip et
  incapables de garantir l'identité d'un personnage récurrent d'une vidéo à
  l'autre. Conservés comme étalon qualité, pas comme dépendance.
- **Wan2.2-Animate** : très bon pour *remplacer* un personnage dans une vidéo
  existante ; ce n'est pas notre besoin (nous créons le présentateur).
- **Helios** : intéressant pour la durée (minute-scale), mais notre grammaire est
  la courte séquence assemblée ; un plan de 40 s est plus dur à corriger qu'un
  plan de 6 s.
- **ComfyUI comme socle** : voir §2.
- **Framework multi-agents** : aucun besoin mesurable. Un directeur unique.

## 7. Ce qui reste explicitement non vérifié

- Les temps de génération réels des trois moteurs (aucun GPU dans
  l'environnement de développement).
- La qualité perçue de LongCat 1.5 contre InfiniteTalk sur notre présentateur.
- La stabilité de l'identité entre plans LTX (test C).
- Les drapeaux exacts de `a2vid_two_stage` (le module existe, ses options n'ont
  pas été exécutées ; le workflow le signale comme « à confirmer sur GPU »).

Ces points sont dans `BENCHMARKS.md` avec le protocole pour les lever, et dans
`STATE.md` avec leur statut.
