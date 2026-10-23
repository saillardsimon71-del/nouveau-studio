# Production SiteQuiVend du 23 octobre 2026

Recette du film publicitaire livré, sans modification de l'architecture du Studio. Les MP4 et les images restent dans le dossier de livraison local, hors Git. Les paramètres et les sommes de contrôle sont dans `docs/productions/sitequivend-2026-10-23.json`.

La production utilise les trois images d'ouverture originales décrites dans le dossier de livraison, une vidéo Pexels licenciée et l'extrait musical crédité. Les scripts attendent ces fichiers dans un dossier de travail passé avec `--work` :

- `produit-reference.png`, `restaurant-reference.png`, `villa-reference.png`.
- `source-interieur-5s.mp4`, normalisé en 768x1344, 24 fps, 121 images.
- `ascension.mp3`, téléchargé depuis la page officielle de Scott Buckley.
- `fonts/Manrope-Medium.ttf`, `Manrope-Bold.ttf`, `Manrope-ExtraBold.ttf` et la licence OFL.

Dans l'environnement validé de cette session, depuis la racine du dépôt :

```powershell
$env:PYTHONUTF8 = '1'
$productionWork = 'C:\chemin\vers\sitequivend-ad'
$productionOutput = 'C:\chemin\vers\livraison-sitequivend'
python scripts/production/sitequivend_shots.py --work $productionWork
modal run scripts/production/sitequivend_voice.py --out $productionWork
python scripts/production/sitequivend_audio.py --work $productionWork
python scripts/production/sitequivend_assemble.py --work $productionWork --output $productionOutput
```

Le premier script réutilise le worker LTX existant, ne relance pas une prise dont le MP4 et les métadonnées complets existent, et ne fait aucun retry automatique. Chaque appel GPU est limité à 900 secondes. Le script de voix fonctionne uniquement sur CPU et conserve ses trois petits fichiers de modèle dans le volume séparé `pvs-commercial-audio-models`.

Le script audio utilise Whisper local pour vérifier le texte et obtenir les horodatages. Le script de montage utilise `AssemblyEngine`, les fonctions ASS/SRT et le QC existants. Il produit une version avec sous-titres, une version sans sous-titres, une miniature et les rapports. `--post-only` réutilise le montage assemblé pour corriger seulement les textes et les sous-titres.

Cette recette nécessite ffmpeg avec libass, Modal, Pillow, NumPy, SciPy, fontTools et openai-whisper dans l'environnement local. Les versions effectivement utilisées sont consignées dans le manifeste. Les images préparatoires ont été générées avec l'outil imagegen, pas avec les scripts.

Conserver les crédits du fichier `Texte-de-publication.txt` lors de la diffusion. Le film illustre une transformation créative ; le mobilier et les détails d'une propriété peuvent être réinterprétés par le video-to-video.
