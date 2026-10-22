# Architecture

## Principe

Une application, un process, un GPU à la fois, une seule frontière avec le monde
extérieur : le contrat `Engine`.

```
   Navigateur
      │  HTTP (même origine)
      ▼
┌────────────────────────────────────────────────────────────────┐
│ app (FastAPI, 1 process)                                       │
│                                                                │
│  api.py        routes, validation, upload                      │
│  director.py   brief → storyboard (LLM JSON validé | template) │
│  jobs.py       file SQLite → pool de threads → Engine          │
│  qc.py         contrôles automatiques + checklist humaine      │
│  cost.py       GPU-secondes, tarifs, coût par export           │
│  media.py      probe (PyAV), ffmpeg, loudness, détecteurs       │
│  graphics.py   ASS/SRT (sous-titres, titres)                   │
│  db.py         SQLite (WAL, autocommit, 1 connexion/thread)    │
└───────────────┬────────────────────────────────────────────────┘
                │  Engine.run(EngineRequest) -> EngineOutput
     ┌──────────┴───────────┬──────────────────┬───────────────┐
     ▼                      ▼                  ▼               ▼
 ltx_native           longcat_avatar      chatterbox /    ffmpeg_assembly
 (CLI GPU)            (torchrun GPU)      voxcpm2 (CLI)   (CPU, local)
                                                  │
                                          comfyui (HTTP, optionnel)
                                          mock_* (simulation, toujours dispo)
```

## Le contrat `Engine`

```python
class Engine(ABC):
    info: EngineInfo                      # nom, type, capacités, vérifié/simulé
    def available() -> (bool, str)        # poids présents ? recoin joignable ?
    def run(request: EngineRequest, ctx) -> EngineOutput
```

`EngineRequest` porte : le type, un dossier de sortie, le projet, le plan, les
paramètres, et les **entrées** (image de référence, audio, vidéo source).
`EngineOutput` porte : les artefacts produits, l'usage GPU, des diagnostics.

Trois conséquences voulues :

1. **Remplacer un moteur = écrire une classe.** Aucune logique produit ne connaît
   LTX ni LongCat.
2. **Un moteur indisponible ne casse pas l'application.** `registry.resolve()`
   essaie l'engine demandé, puis les alternatives du même type, puis — si
   `PVS_ALLOW_MOCK=1` — la simulation. Le repli est **journalisé et remonté**
   (`jobs.error`, drapeau `simulated`, badge dans l'UI). Jamais silencieux.
3. **Les moteurs réels tournent hors du process API** (`subprocess` vers les CLI
   ou `torchrun`, ou HTTP vers ComfyUI). L'API reste légère, déployable sur une
   petite VM, et les poids vivent sur un volume GPU.

## Modèle de données

| Table | Rôle | Champs notables |
|---|---|---|
| `projects` | intention | `brief`, `format`, `concept`, `script`, `style_guide`, `music_path` |
| `shots` | un plan ordonné | `kind`, `duration_s`, `dialogue`, `prompt`, `camera`, `transition`, `character_id`, `voice_id`, `selected_artifact`, `qc` |
| `characters` | identité récurrente | `base_image`, `appearance`, `voice_id`, `refs` |
| `voices` | timbre récurrent | `engine`, `language`, `ref_audio` |
| `jobs` | exécution | `type`, `engine`, `status`, `progress`, `provider`, `gpu`, `gpu_seconds`, `cost_usd`, `simulated`, `error` |
| `artifacts` | fichier produit | `kind`, `path`, `bytes`, `meta`, `selected` |
| `exports` | montage final | `spec` (format, sous-titres, musique, `poster_artifact`), `duration_s`, `qc` |
| `cost_events` | comptabilité | `provider`, `gpu`, `gpu_seconds`, `rate_usd_hr`, `usd` |

Le plan est l'unité de travail : c'est lui qui porte l'état (`draft` →
`voiced` → `generated`), le QC, l'artefact sélectionné et l'historique de ses
artefacts. C'est ce qui rend la régénération ciblée possible.

## Exécution asynchrone, sans infrastructure

- `jobs.enqueue()` écrit une ligne `queued`.
- Un thread dispatcher (0,4 s de latence max) alimente un `ThreadPoolExecutor`
  dimensionné par `PVS_MAX_WORKERS` (1 par défaut : un GPU = un job vidéo).
- Chaque engine rend la main en écrivant sa progression (`ctx.log`).
- Au démarrage, les jobs `running` sont remis en file (`PVS_REQUEUE_ON_BOOT`) :
  un redémarrage de pod ne perd pas la production.
- L'annulation est coopérative : `ctx.check_cancelled()` interroge la base, le
  runner termine le sous-processus.
- Les logs de job sont des fichiers (`data/tmp/<job>.log`) exposés par
  `/api/jobs/{id}/log`.

Pas de Redis, pas de Celery, pas de worker séparé. Le volume réel — quelques
dizaines de jobs par jour — ne le justifie pas.

## Pipelines composés

Deux types de jobs dépassent un seul appel de moteur, et sont orchestrés dans
`jobs.py` (pas dans une couche « workflow » abstraite) :

**Avatar** : `dialogue → TTS (chatterbox/voxcpm) → audio → avatar engine
(reference_image + audio) → clip`. Si un audio existe déjà pour le plan, il est
réutilisé (`force_tts` permet de forcer). Le job porte les deux artefacts.

**Retake** : `clip source → LTX retake [start, end) → snippet → splice_region()`
réinsère la zone corrigée dans le clip original (ffmpeg concat 3 segments). Le
clip d'origine n'est jamais modifié : l'artefact régénéré s'ajoute à l'historique
du plan, ce qui permet de comparer et de revenir en arrière.

## Montage

`AssemblyEngine` fait, dans l'ordre :

1. probe de chaque plan, durée effective = `min(durée plan, durée réelle du clip)`
   (jamais d'étirement : cela casserait la synchro son/image) ;
2. **normalisation deux passes** (scale/crop 1080×1920, fps constant, audio 48 kHz
   stéréo) vers des fichiers intermédiaires — un seul mauvais fichier ne tue plus
   tout l'export, et `xfade` exige un débit constant ;
3. concaténation `concat` ou chaîne `xfade`/`acrossfade` ;
4. sous-titres ASS incrustés (alignés sur la timeline réelle) + sidecar `.srt` ;
5. lit musical optionnel (`sidechain`-free, gain paramétré, fades) puis
   `loudnorm` à la cible (‑14 LUFS par défaut) ;
6. H.264 CRF 18, AAC 192 k, faststart, + poster JPEG + `filtergraph.txt`
   (le graphe exact est conservé avec l'export pour l'audit).

## Contrôle qualité

Deux niveaux, jamais confondus :

- **Automatique** (`qc.inspect_clip`) : conteneur lisible, durée attendue, ratio,
  fps, présence audio, fréquence d'échantillonnage, résolution, segments noirs
  (`blackdetect`), images figées (`freezedetect`), loudness (EBU R128).
  Verdict `pass` = « aucun défaut d'emballage détecté ».
- **Humain** : identité, lip-sync, jeu, respect du prompt. Exposé comme checklist
  attachée au plan. Aucun modèle ne prétend l'évaluer.

C'est volontaire : promettre une détection IA fiable des visages déformés coûte
cher, se trompe souvent, et donne une fausse assurance.

## Coûts

Chaque job enregistre son `provider`, son `gpu`, ses `gpu_seconds` et le tarif
appliqué (`rate_card` surchargeable par `PVS_RATE_<PROVIDER>_<GPU>`). Les
**tentatives échouées sont facturées aussi** : c'est la seule façon d'obtenir un
« coût par vidéo acceptée » honnête. `cost.project_summary()` calcule
`cost_per_export_usd` et `attempts_per_success`.

## Sécurité et exploitation

- Une seule origine : l'UI et l'API sont servis par le même process. CORS est
  ouvert uniquement pour le serveur de dev Vite.
- Les uploads sont limités par extension et taille (800 Mo).
- Aucune clé n'est stockée en base : tout passe par l'environnement.
- Les fichiers générés vivent dans `data/` (ignoré par Git) ; les exports de
  démonstration publiés vivent dans `data/exports/` (versionné volontairement).
