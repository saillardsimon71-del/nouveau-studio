# Statut de production — 2026-10-27

## État : `READY_TO_RUN_CPU_CHECK_AND_VOICE_SAMPLE`

- `voice.mp3` est utilisé comme référence vocale, jamais comme dialogue.
- Le workflow GitHub Actions prépare et teste Chatterbox V3 **sur CPU** dans Modal, puis génère l'échantillon anglais 5–8 s sur A10G. Le sample-stage s'arrête avant toute animation vidéo.
- Les poids Chatterbox sont mis en cache dans le volume Modal dédié `pvs-english-voice-model-cache`.
- Les nouveaux audios sont enregistrés dans le volume privé Modal `pvs-english-talking-head-private`, hors du dépôt public et sans upload GitHub Actions Artifact.
- Récupération après génération : `modal volume get pvs-english-talking-head-private english-talking-head-20261027/voice_sample.wav ./voice_sample.wav`.
- L'étape `render` exige les choix explicites `voice_approved=yes` et `confirm_gpu_spend=yes`. Elle est bloquée jusqu'à l'écoute/comparaison humaine du sample.
- Le worker LongCat passe en continuation pour un long discours, conserve le cadrage de la photo et remuxe le WAV synthétisé. Le rendu multi-segment de 45–60 s reste expérimental.

Aucun run Modal ni échantillon n'a encore été produit. Les changements doivent d'abord être poussés, puis le workflow `English Talking-Head — cloned voice sample and avatar` peut être lancé avec `stage=voice_sample`. La similarité vocale doit être évaluée à l'écoute; aucun résultat automatique ne peut la garantir.
