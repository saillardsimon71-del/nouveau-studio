# Plan d'implémentation, 25 octobre 2026

Objectif : enrichir le Director existant par des connaissances sourcées, sans rendu GPU.

Architecture : fichiers JSON versionnés dans `studio/ad-references`, modules Python
dans `backend/app/ad_references`, activation explicite dans `director.propose` et
son API. Stockage des analyses privées dans le `data_dir` existant. Pas de service,
de base vectorielle ni d'agent ajouté.

- [x] Catalogue de 15 campagnes : schéma Pydantic, accès et droits explicites,
  observations documentaires séparées des observations vidéo horodatées.
- [x] Analyse CPU : réutiliser `media.probe/run_ffmpeg`, Whisper déjà employé dans
  `sitequivend_audio.py`, cuts, échantillons, mesures vocales et import WhisperX.
- [x] Recherche locale bornée, recettes documentaires provisoires et extraction
  de recettes depuis les observations de médias autorisés.
- [x] Intégration désactivable dans les modes local et LLM du Director ; prompts
  texte H3, locuteurs, durée de parole et provenance conservés par plan.
- [x] Évaluation et comparaison de rapports compatibles ; gabarit ÉCLAT sans score
  inventé ; trois démonstrations locales et documentation d'audit/licences.
- [x] Tests des cas muets, musique seule, timestamps incomplets, dialogue trop
  long, catalogue absent/invalide, mode désactivé et persistance API ; suite complète.
- [ ] Commits, push et PR sans fusion ni déclenchement de production.

Les publicités de marque restent des liens documentés. Ni vitesse vocale ni jeu
d'acteur ne seront déduits d'un descriptif. Les plages de débit des démonstrations
sont des choix éditoriaux, pas des statistiques des campagnes.

État initial : commit `996776d95ccdeb6cfc07bbbd5c7e07681b9d2d2e`, 81 tests,
un échec préexistant : `test_cpu_entrypoint_never_defines_a_cuda_image`, causé par
un faux `modal` conservé globalement par `test_modal_h3_local.py`.

Validation locale finale : 112 tests réussis en 48,29 s dans un environnement
virtuel avec les dépendances déclarées du backend, plus librosa 0.11.0.
La transcription Whisper réelle du signal de test et l'import/évaluation/
auto-comparaison par CLI ont également été exécutés. La revue indépendante a
identifié quatre défauts corrigés avec tests : locuteurs A/B, transfert de photo,
exclusion des débits non vérifiés et validation des règles de recette.

Choix : FFmpeg déjà présent plutôt qu'une dépendance PySceneDetect ; pas de
service Qwen déployé sans besoin d'inférence autorisée. Les observations visuelles
et marketing détaillées restent à annoter sur les futurs médias autorisés.
