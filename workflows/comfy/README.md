# Workflows ComfyUI

ComfyUI est ici un **backend d'exécution optionnel**, pas l'architecture du studio.
Le studio ne contient aucun graphe inventé : un workflow doit être exporté depuis
l'interface ComfyUI, puis déposé dans ce dossier.

## Procédure

1. Sur la machine GPU, lancer ComfyUI avec les nœuds LTX :
   ```bash
   git clone https://github.com/comfyanonymous/ComfyUI /opt/ComfyUI
   cd /opt/ComfyUI && python -m pip install -r requirements.txt
   git clone https://github.com/Lightricks/ComfyUI-LTXVideo custom_nodes/ComfyUI-LTXVideo
   python main.py --listen 0.0.0.0 --port 8188
   ```
2. Construire / charger un workflow dans l'UI, vérifier une génération manuelle.
3. **Workflow → Save (API Format)**. Cela produit un JSON de type
   `{"<node_id>": {"class_type": "...", "inputs": {...}}}`.
4. Le déposer ici sous l'un des noms attendus par l'adaptateur :
   - `ltx_t2v.json` — texte → vidéo
   - `ltx_i2v.json` — image → vidéo (avatar / cohérence)
   - `avatar_infinite_talk.json` — audio → vidéo (talking head)
   - `upscale.json` — post-traitement
5. Remplacer les valeurs variables par les jetons suivants :
   `__PROMPT__`, `__IMAGE__`, `__AUDIO__`, `__SEED__`, `__FRAMES__`, `__WIDTH__`,
   `__HEIGHT__`, `__FPS__`.
6. Configurer le studio :
   ```bash
   export PVS_COMFY_URL=http://gpu-host:8188
   ```
   puis dans l'UI, choisir le moteur `comfyui` et passer `workflow` dans les
   paramètres du plan.

## Pourquoi cette séparation

Les graphes ComfyUI sont fragiles (noms de nœuds, versions de custom_nodes) et
illisibles en diff Git. Les garder hors du code applicatif permet de changer de
graphe sans toucher au studio, et de comparer un même plan entre `ltx_native`
(CLI) et `comfyui` (graphe) sans dupliquer la logique produit.

Aucun fichier `*.json` n'est fourni par défaut : nous n'avons pas exécuté
ComfyUI dans cet environnement, et un graphe non testé serait pire qu'aucun
graphe.
