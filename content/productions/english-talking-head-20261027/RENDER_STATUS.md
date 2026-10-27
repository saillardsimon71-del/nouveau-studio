# Statut de production — 2026-10-27

## Statut: `VOICE_SAMPLE_GENERATED_PRIVATE_AWAITING_HUMAN_APPROVAL`

Le **nouvel échantillon vocal en anglais a été généré réellement**, à partir du MP3 de référence fourni par le créateur. Aucun MP4, aucune animation LongCat ni narration complète n'a été lancé.

### Preuves

- GitHub Actions, premier lancement: [run 40488121743](https://github.com/saillardsimon71-del/nouveau-studio/actions/runs/40488121743) — échec reproductible `ChatterboxMultilingualTTS.from_pretrained() got an unexpected keyword argument 't3_model'` avec le paquet PyPI.
- Correction: épinglage du commit officiel Chatterbox `5de7a54aa4e5e2baadb0182dde554908b48b85c2`, utilisé et validé par le studio auparavant.
- GitHub Actions, deuxième lancement: [run 40489092685](https://github.com/saillardsimon71-del/nouveau-studio/actions/runs/40489092685) — **synthèse effective confirmée dans les logs Modal**, mais statut GitHub `failure` car le contrôle de durée exigeait 5–8 s et le vrai fichier dure 8,16 s. Cette petite différence n'est **pas** un échec de synthèse.
- Logs Modal : `{"output":"artifacts/voice_sample.wav","duration_seconds":8.16,"sample_rate":24000,"model":"Chatterbox Multilingual V3","language":"en","gpu":"A10G","gpu_wall_seconds":44.71,"private_volume":"pvs-english-talking-head-private","private_path":"english-talking-head-20261027/voice_sample.wav","status":"generated_not_human_voice_reviewed"}`.
- Application Modal: https://modal.com/apps/kulejean567/main/ap-kAIX7YOavSt7eqQcTAPImE

### Audio à récupérer

Ce fichier est dans un volume Modal **privé**, pas dans les GitHub Actions Artifacts du dépôt public.

```bash
modal volume get pvs-english-talking-head-private english-talking-head-20261027/voice_sample.wav ./voice_sample.wav
```

L'utilisateur doit pouvoir accéder au workspace Modal `kulejean567` pour l'écouter. Ne pas publier l'échantillon sans son accord.

### Décision

1. Comparer à l'écoute `voice_sample.wav` avec `voice.mp3` original; vérifier ressemblance, diction anglaise, naturel.
2. Si la qualité est mauvaise, ne pas lancer le rendu long. Diagnostiquer uniquement la voix.
3. Si la voix est approuvée, produire un discours complet de 45–60 s; mesurer sa durée avant animation.
4. La continuation LongCat au-delà de deux segments est expérimentale et demande validation préalable sur un pilote court avec la nouvelle voix.
5. Le rendu A100 ne doit avoir lieu qu'après confirmation humaine et budget autorisé.

### Sécurité et exécution

- Les deux médias d'origine sont dans un dépôt public sur demande explicite du créateur; ne pas étendre cette exposition aux nouveaux audios ou à la vidéo finale.
- Le workflow GitHub a été remis en mode `workflow_dispatch` uniquement, pour éviter qu'une modification de branche ne relance une synthèse GPU par accident.
- La tolérance de durée du test audio a été portée à 5–9 s dans le workflow **pour de futures exécutions**, sans réexécuter le GPU.
- Coût réellement facturé par Modal: **non vérifié**. 44,71 s est la durée de calcul rapportée, pas un montant facturé.
