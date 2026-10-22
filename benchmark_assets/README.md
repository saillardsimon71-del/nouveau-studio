# Inputs de benchmark

Ces deux fichiers sont les **entrées réelles** des tests A (cinématique), B (avatar
qui parle en français) et C (même personnage sur 3 plans). Aucun benchmark ne doit
tourner sans eux : sinon on mesure la qualité sur des entrées inventées.

| Fichier | Rôle | Format attendu |
| --- | --- | --- |
| `character_reference.png` | le personnage de référence pour la continuité (Test C) et l'ancrage du visage | PNG, vertical 9:16, ≥ 512 px sur le petit côté, ≤ 24 MiB |
| `voice_reference_fr.wav` | la voix française à cloner pour l'avatar parlant | WAV PCM 16 bits, ≥ 16 kHz, 3-60 s, non silencieux |

Vérification (bloque le run si un fichier manque ou est invalide) :

```bash
python scripts/check_benchmark_assets.py
```

## 1. `character_reference.png` — déjà fourni

Le fichier actuel est un **portrait synthétique généré pour les tests**, pas une
personne réelle et pas vous : il sert uniquement à vérifier la continuité d'un
plan à l'autre. Si vous voulez tester *votre* visage, remplacez-le par une photo
verticale (buste, regard caméra, lumière douce, sans texte).

Procédure depuis l'iPhone, sans ordinateur :

1. Enregistrer ou choisir une photo verticale dans Photos.
2. Ouvrir Safari → `github.com/saillardsimon71-del/nouveau-studio` → dossier
   `benchmark_assets` → bouton **Add file ▸ Upload files**.
3. Choisir la photo, la renommer `character_reference.png` (iOS permet de
   renommer avant l'envoi ; exporter en PNG depuis Photos → Fichiers si besoin).
4. **Commit changes**, branche `arena/d40d9dd5-nouveau-studio`.

Si la photo n'est pas au format 9:16 exact, ce n'est pas bloquant : le worker
redimensionne en interne, le validateur exige seulement le vertical.

## 2. `voice_reference_fr.wav` — à fournir

Le clone de voix a besoin de 10 s de français naturel. Enregistrement iPhone :

1. App **Dictaphone** → enregistrer ~10 s, ton normal, sans musique :
   > « Et si tu pouvais automatiser toutes ces tâches qui te font perdre du temps ?
   > Ce soir, tu pourrais enfin rentrer chez toi à l'heure. »
2. Partager ▸ **Enregistrer dans Fichiers** → dossier « Sur mon iPhone ».
3. Dans Fichiers, appui long sur l'enregistrement ▸ **Renommer** →
   `voice_reference_fr.wav` (le Dictaphone produit du `.m4a` : partagez-le d'abord
   vers **Fichiers**, puis renommez l'extension en `.wav` *uniquement* si la
   conversion a eu lieu. Sinon, utilisez l'option **Convertir** d'iOS 17+
   (partage ▸ Options ▸ Format ▸ WAV) avant de renommer.)
4. Safari → dépôt GitHub → `benchmark_assets` → **Add file ▸ Upload files** →
   sélectionner le `.wav` → **Commit changes**.

Contrôle qualité à l'oreille avant d'envoyer : une seule voix, pas de bruit de
fond, pas de musique, pas de coupure au début.

> Si vous ne voulez pas utiliser votre voix : n'importe quelle voix française
> dont vous détenez les droits fait l'affaire (la vôtre, un comédien, un
> enregistrement libre de droits). Le fichier ne quitte jamais le dépôt privé de
> votre choix ; ici le dépôt est public, donc n'utilisez pas une voix que vous ne
> voulez pas voir publique.

## Ce que le validateur refuse

- PNG non vertical, < 512 px, > 24 MiB, ou corrompu.
- WAV < 16 kHz, non PCM 16 bits, < 3 s ou > 60 s, quasi silencieux.
- Toute absence de fichier : le workflow s'arrête avant de lancer le GPU.
