# État réel du studio

Dernière mise à jour : 2026-10-22. Environnement de développement : Debian,
**2 vCPU, 3 Go de RAM, aucun GPU**. Toutes les mesures ci-dessous viennent de cet
environnement, sauf mention explicite.

Règle appliquée partout : *« ça compile » n'est pas « ça marche »*, et *« ça
marche dans le pipeline »* n'est pas *« la qualité est atteinte »*. Les deux sont
séparés ci-dessous.

---

## Ce qui fonctionne réellement (exécuté, observé)

| Fonction | Preuve | Mesure |
|---|---|---|
| API complète (projets, plans, personnages, voix, artefacts, exports, coûts) | 21 tests pytest, tous verts | ~43 s |
| Directeur créatif local (template FR) | test unitaire + démo | storyboard de 5 plans, 35,0 s |
| Directeur IA (LLM JSON validé + retry) | code + fallback testé | **appel réseau réel non exécuté** (pas de clé) |
| File de jobs, progression, reprise après redémarrage, annulation | tests API | job complet en 3–12 s (simulation) |
| Génération vidéo simulée (plaque de test) | démo + tests | 1080×1920, 30 fps, audio 48 kHz |
| Avatar « pipeline » (TTS → moteur avatar → clip) | test API | les 2 artefacts produits, log explicite |
| Montage ffmpeg multi-plans | test + démo | 5 plans → 33,6 s, xfade, 1080×1920 |
| Sous-titres incrustés (ASS) + `.srt` | vérifié **image par image** (pixels clairs dans la frame) | cues ≤ 60 caractères, dans la fenêtre du plan |
| Musique + loudness | démo | **−14,0 LUFS** intégré, vrai pic ≤ −1,5 dBTP |
| QC automatique | démo | 9 contrôles, verdict `pass` |
| Suivi de coût (y compris échecs) | tests | coût 0,00 $ en local (CPU) |
| UI React (projets, studio, personnages, moteurs/coûts) | build TypeScript sans erreur, servie par l'API | 167 kB JS, 8,9 kB CSS |

### Mesures de l'export de démonstration

```text
fichier      data/exports/demo_simulation_vertical.mp4
durée        33,60 s
image        1080×1920 @ 30 fps, H.264 CRF 18, AAC 192 kbps 48 kHz
taille       4,6 Mo
loudness     -14,0 LUFS (cible -14)
QC           9/9 contrôles pass (conteneur, durée, ratio, fps, audio, taux, noirs, images figées, loudness)
temps        ~34 s de montage sur 2 vCPU (5 plans)
coût         0,00 $ (CPU local)
```

Détail honnête : ce fichier est **100 % simulation**. Il prouve l'assemblage, la
timeline, les sous-titres, le mixage et le QC. Il ne prouve rien sur la qualité
des modèles.

---

## Ce qui est écrit mais non exécuté (bloqué : pas de GPU)

| Composant | Ce qui est prêt | Ce qui manque pour valider |
|---|---|---|
| `ltx_native` (LTX-2.5 DFR / distilled / retake) | commandes complètes, chemins de poids, quantification, offload, grille causale 8k+1, sortie H.264 | 1× H100 ou A100 80 Go + 66 GiB de poids |
| `longcat_avatar` (LongCat-Video-Avatar 1.5) | input JSON, `torchrun`, `--use_distill --use_int8`, segments, résolution | A100 80 Go + poids 1.5 + voix |
| `chatterbox` / `voxcpm2` | script CLI + `--check` (import torch), paramètres `exaggeration`/`cfg_weight` | venv TTS + 4–8 Go VRAM (CPU possible pour Chatterbox) |
| `comfyui` | client `/prompt` → `/history` → `/view`, substitution de jetons | un workflow **exporté depuis l'UI** (aucun graphe inventé livré) |
| `a2vid_two_stage` | recette YAML marquée « flags à confirmer » | première exécution réelle |

**Aucune vidéo générée par un modèle n'existe dans ce dépôt.** Toute capture,
tout rendu, tout chiffre de qualité produit par un modèle serait une invention.

---

## Blocages actuels (retournés par `/api/system`)

```
Aucun moteur vidéo réel disponible (GPU + poids LTX-2.5 requis).
Aucun moteur avatar réel disponible (GPU + poids LongCat-Video-Avatar 1.5 requis).
Aucun moteur de voix réel disponible (Chatterbox/VoxCPM2 non installés).
Aucune clé LLM configurée : le directeur utilise son template local.
```

Ces messages sont volontairement visibles dans l'UI (page *Moteurs & coûts*) et
dans chaque job. Un job qui retombe sur la simulation porte `simulated = 1`, un
badge « simulation » sur le plan et une phrase dans `jobs.error`.

---

## Jalons

### Jalon 1 — un avatar photoréaliste parle français ⏳
- Pipeline : ✅ (voix → avatar → clip → QC), testé avec les moteurs de simulation.
- Rendu réel : ⏳ bloqué GPU. Protocole : `benchmarks/scenarios/test_a_avatar.yaml`.
- Critère de sortie : lip-sync, identité et voix ≥ 3/5 sur 3 lectures humaines.

### Jalon 2 — un plan cinématographique premium exporté ⏳
- Assemblage et export : ✅ (mesuré ci-dessus).
- Rendu réel LTX : ⏳ bloqué GPU. Deux variantes prêtes (DFR qualité, distilled brouillon).

### Jalon 3 — même personnage sur plusieurs plans ⏳
- Mécanique : ✅ image de référence par personnage, réutilisée par chaque plan,
  reprise dans l'historique des artefacts.
- Preuve d'identité : ⏳ nécessite les modèles + jugement humain.

### Jalon 4 — publicité verticale 30–45 s assemblée ✅ **structurellement**
- 5 plans, avatar + B-roll + capture d'écran, sous-titres, musique, montage : ✅
  produit et mesuré (`data/exports/demo_simulation_vertical.mp4`).
- Avec de vrais rendus : ⏳ dépend des jalons 1–3.

### Jalon 5 — deuxième vidéo avec le même personnage ✅ **structurellement**
- Projets indépendants, personnage et voix globaux réutilisables : ✅.
- Sans reconstruction manuelle : ✅ (le brief suffit ; le storyboard se régénère).
- Qualité réelle : ⏳ dépend des jalons 1–3.

---

## Défauts observés et corrigés pendant la construction

1. **Sous-titres incrustés deux fois** (moteur puis montage) → un moteur livre une
   plaque propre ; tout le texte est en post-production.
2. **Export impossible** dès qu'un plan avait un débit variable (`xfade` refuse un
   fps non constant) → normalisation en deux passes.
3. **Timeline rétrécie de 34 s à 27 s** quand la voix simulée était plus courte
   que le plan → la durée du plan est une décision éditoriale, l'audio est padé.
4. **État de plan non rafraîchi** après un job : la base restait sur un instantané
   WAL antérieur et l'UI voyait un plan « draft » avec un clip prêt → autocommit,
   curseurs fermés, et le plan est mis à jour **avant** le passage du job en
   `succeeded` (l'UI sonde le statut du job).
5. **Moteur TTS choisi sans vérifier ses dépendances** (échec `torch` en cours de
   job) → `available()` exécute `--check` avec cache court.

Ces cinq défauts ont été trouvés en regardant les frames et les bases, pas en
relisant le code. C'est la raison pour laquelle les tests d'export inspectent les
pixels.

---

## Limites assumées

- Le QC automatique ne juge pas la qualité artistique. Identité, lip-sync et jeu
  restent humains : c'est explicite dans l'UI et dans l'API.
- Les estimations de coût des benchmarks sont des hypothèses issues des vitesses
  publiées, pas des mesures. Elles sont étiquetées comme telles.
- L'adaptateur `a2vid` de LTX porte la mention « flags à confirmer ».
- Le repérage de la sortie vidéo de LongCat se fait par fichier le plus récent :
  robuste mais à ajuster dès la première exécution réelle (chemin exact du script
  amont inconnu).
- Mono-utilisateur, mono-processus, mono-GPU par défaut. Ce n'est pas une limite
  technique cachée : c'est le dimensionnement du besoin actuel.
- Aucun orchestrateur de pods. Voir `GPU.md`.
