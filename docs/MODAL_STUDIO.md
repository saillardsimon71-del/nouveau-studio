# Studio avec les moteurs Modal

Les applications du nouveau studio sont `pvs-ltx` et `pvs-longcat-avatar`, dans
`kulejean567/main`. LongCat utilise exclusivement `pvs-longcat-models`.
L'ancienne application `studio-ia-ltx` reste indépendante.

## Lancer l'interface

```powershell
python -m pip install -r backend/requirements-modal.txt
cd frontend
npm ci
npm run build
cd ..
modal profile activate kulejean567
python scripts/run_modal_studio.py
```

Ouvrir http://127.0.0.1:8787. Cliquer sur "Préparer un avatar français", puis
préparer ou importer la voix, l'écouter et valider les mots et le naturel, puis
"Générer". La préparation crée un plan et sélectionne le portrait synthétique
versionné. Elle ne lance aucun GPU. Les identifiants Modal restent côté serveur.
Le lanceur désactive les simulations et la relance automatique des anciens jobs.

Le bouton "Générer" appelle directement la fonction Modal déployée, via la file
de jobs existante. Le résultat, ses métriques et son identifiant d'appel sont
conservés dans `data/projects/<projet>/jobs/<job>/`. Le MP4 est consultable et
téléchargeable dans le plan. Les moteurs LTX et LongCat sont sélectionnables.
Un autre portrait se choisit dans "Personnages & voix", puis dans le plan.

## Limites du pilote validé

- LongCat : un segment, 93 images à 25 images/s, voix de 3,72 s maximum.
- Une voix trop longue échoue avant l'appel GPU ; ne pas l'accélérer pour la faire rentrer.
- Voix enregistrées sélectionnables et import WAV ; transcription et écoute validées avant animation.
- Le parcours diagnostique et la limite expérimentale à deux segments sont décrits dans [HUMAN_PERFORMANCE.md](HUMAN_PERFORMANCE.md). La continuation n'est pas validée par un nouveau rendu et reste désactivée sur l'ancien service.
- LTX : 1 à 15 s, formats 9:16, 16:9 et 1:1.
- Un worker local et un conteneur maximum par moteur ; aucun GPU maintenu chaud.
- Les coûts affichés sont estimés à partir de la durée mesurée et des tarifs
  GPU/CPU/RAM. La facturation Modal inclut aussi le démarrage et les variations de RAM.
- Le contrôle automatique vérifie le conteneur, l'audio et le format. La finesse
  de la synchronisation labiale et le jeu demandent une appréciation visuelle.

## Maintenance et artefacts GitHub

```powershell
modal run -m deploy.modal_avatar_models --mode doctor
# Uniquement si les poids manquent : reprise des fichiers déjà téléchargés.
modal run -m deploy.modal_avatar_models --mode prepare
```

Ces deux commandes utilisent une image CPU qui ne construit jamais CUDA.
Le manifeste contrôle chaque fichier attendu et sa taille.
L'image GPU installe `libsndfile1` par apt et exclut des exigences pip ce paquet
système ainsi que `tritonserverclient`, paquet non publié et inutilisé par l'inférence.

Le workflow `modal-avatar.yml`, étape `collect`, récupère un appel Modal terminé
avec son `call_id` et le publie en artefact pendant 30 jours, sans nouveau rendu.
L'étape `render` reste disponible pour un test complet avec GPU autorisé.
