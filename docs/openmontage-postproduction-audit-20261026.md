# Audit OpenMontage → Nouveau Studio — postproduction (2026-10-26)

## Décision

**Ne pas remplacer Nouveau Studio par OpenMontage.** Ajouter un seul élément manquant à l'export standard : une atténuation de la musique sous les dialogues, **désactivée par défaut**. Aucun changement au moteur LTX/Modal, aux prompts, à la synthèse vocale ou aux scripts des productions existantes.

## Comparaison factuelle

- `backend/app/engines/assembly.py` : FFmpeg, normalisation géométrique et FPS, concat/xfade, musique, sous-titres ASS/SRT, loudnorm et miniature **existent déjà**.
- `backend/app/qc.py` : conteneur, durée, FPS, ratio, audio, noir, gel d'image, loudness, points de contrôle humains **existent déjà**. `backend/app/jobs.py` appelle `qc.inspect_export` et conserve le résultat dans la base.
- `scripts/production/sitequivend_assemble.py` : un script publicitaire spécifique utilise déjà `sidechaincompress`, mais cette fonction manquait dans l'export générique de l'interface.
- OpenMontage : `tools/video/video_compose.py`, `tools/video/video_stitch.py`, `remotion-composer`, `tools/audio` et `pipeline_defs/cinematic.yaml`. Ces modules ont une portée beaucoup plus large. Leur import direct ajouterait de la complexité et des obligations de licence pour un faible gain immédiat.

## Changement isolé

- Case optionnelle « Atténuer automatiquement la musique pendant les dialogues ».
- Lorsque musique et audio de dialogue sont présents, le bus musical passe dans `sidechaincompress`, piloté par la piste d'origine ; la voix reste au volume initial, et le résultat passe dans le normaliseur existant.
- Sans musique, sans dialogue renseigné ou case désactivée, le comportement existant est conservé.
- `diagnostics.music_ducking` décrit ce qui a réellement été appliqué.
- Pas de génération GPU, pas d'API payante, pas de déploiement.

## Tests et validation

- Tests nouveaux dans `tests/test_assembly.py` : rendu avec musique et dialogues ; rendu sans musique malgré le bouton activé.
- Smoke test FFmpeg **du graphe audio uniquement** exécuté le 2026-10-26 : sortie WAV de 2 s décodable.
- Exécution de la suite de tests et écoute comparative **à confirmer via CI et essai local** ; il n'existe pas de preuve d'amélioration perceptuelle par écoute à ce stade.
- Les vidéos Maison 01 / ÉCLAT 02 / PULSE 01 sont issues de scripts de production dédiés : elles ne sont **pas** modifiées par cette PR.

## Proposition de go/no-go

1. Vérifier les tests CI.
2. Réexporter le même petit spot avec une piste musicale et une voix, option OFF puis ON.
3. Si la compréhension de la voix n'est pas supérieure, ne pas activer par défaut et considérer ce travail comme non prioritaire.
4. Prospection commerciale inchangée.

## Source et licence

OpenMontage : https://github.com/calesthio/OpenMontage — AGPL-3.0. **Aucune copie de code OpenMontage dans ce patch.** Réutilisation d'un filtre FFmpeg standard déjà présent dans le code SiteQuiVend. L'obligation d'analyser la licence demeure pour toute future importation directe.
