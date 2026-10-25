# Human Performance - état vérifié le 25 octobre 2026

La voix est validée par l'utilisateur. La qualité humaine de l'animation n'est pas démontrée. L'unique appel diagnostique a échoué au démarrage du conteneur, avant l'inférence. Aucun nouveau MP4 n'a été produit. Le défaut d'empaquetage a ensuite été corrigé et vérifié sur CPU, sans second appel GPU.

## Parcours de production

Brief -> Script -> Voix validée -> Animation -> Montage -> Contrôle qualité.

- Le Director conserve les plans avatar, le personnage choisi et les intentions. Les références enrichissent les instructions sans imposer H3. Les nouveaux avatars du Director et la démonstration utilisent `performance_mode=voice_first`.
- Le Studio propose les voix enregistrées et l'import WAV. La piste importée ou synthétisée est conservée en WAV PCM16 mono 16 kHz. L'original importé est conservé séparément.
- `backend/app/voice.py` conserve durée, SHA-256, locuteur, transcription, mesures disponibles et intentions. `PVS_ASR_MODEL` désigne un checkpoint Whisper `.pt` local existant. Aucun modèle ASR n'est téléchargé automatiquement.
- Une écoute approuvée et une transcription exacte sont nécessaires. Sans ASR configuré, l'opérateur doit saisir les mots réellement entendus. Cette attestation humaine ne constitue pas une détection automatique des mots. Les mesures ASR précédentes restent conservées après revue du même WAV.
- L'API bloque la mise en file sans voix validée. Le runner vérifie à nouveau le fichier et le dialogue avant de résoudre le moteur. Un changement de WAV ou de texte invalide l'autorisation d'animation.
- Le WAV sélectionné est transmis à l'avatar, même si un ancien client envoie `force_tts`. La durée du son pilote le rendu. Les métadonnées vidéo identifient le WAV utilisé ; le montage refuse une vidéo liée à une autre voix.
- `legacy` conserve le parcours des anciens projets. `native` permet encore les productions audiovisuelles natives, notamment H3. La sélection d'un WAV impose le parcours audio-conditionné. Un plan produit silencieux reste une génération vidéo sans TTS.

## LongCat : implémentation et limites

Le worker reste sur le code officiel épinglé à `6b3f4b8582a8bc3f20f795735f5383716c4ba794`, INT8, 8 pas distillés, 480p. Aucun changement de poids ou de quantification.

La continuation officielle réutilise le contexte vidéo et latent via `generate_avc`. A 25 fps, le premier segment comporte 93 images et le second apporte 80 images uniques après retrait des 13 images de contexte : 173 images, soit 6,92 s. Le worker demande cette continuation et sélectionne précisément `video_continue_2.mp4`. Il ne concatène pas deux générations indépendantes. [Source officielle épinglée](https://github.com/meituan-longcat/LongCat-Video/blob/6b3f4b8582a8bc3f20f795735f5383716c4ba794/run_demo_avatar_single_audio_to_video.py).

Le montage final recadre en 720 x 1280 et remuxe le WAV source en AAC, sans TTS ni changement de vitesse. Le nombre d'images est arrondi au supérieur à 25 fps, soit moins de 40 ms de silence final ajouté si nécessaire. La compression AAC n'est pas une copie binaire du WAV ; son SHA-256 identifie la source conservée.

La capacité distante reste limitée par défaut au service existant à un segment. `PVS_MODAL_AVATAR_APP` sélectionne un worker isolé et `PVS_MODAL_AVATAR_MAX_SEGMENTS=2` active l'envoi du quatrième argument au worker compatible. Ne pas activer ce paramètre sur un ancien déploiement à trois arguments. Aucun service existant n'a été redéployé pendant cette mission.

La logique à deux segments passe les tests CPU ; sa continuité visuelle et son lip-sync ne sont pas validés par un nouveau rendu. La voix approuvée dure 3,68 s et ne nécessite qu'un segment. Elle n'a pas été ralentie ou artificiellement prolongée pour revendiquer un test de 6,92 s.

Le worker inclut explicitement le package `backend`. Son mode `doctor` importe les mêmes helpers sur CPU dans la même image, avant toute tentative diagnostique GPU :

```powershell
$env:PVS_MODAL_AVATAR_APP='pvs-human-performance-preflight'
modal run -m deploy.modal_avatar_worker --mode doctor
```

Le `doctor` des poids reste `modal run -m deploy.modal_avatar_models --mode doctor`. Ni l'un ni l'autre ne prépare de nouveaux poids. Le CLI de diagnostic accepte `--voice-report`, `--receipt` et `--num-segments`. Le rapport doit approuver exactement le WAV ; le reçu est créé exclusivement et empêche une nouvelle soumission avec le même reçu. Le reçu de cette mission reste marqué en échec et ne doit pas être effacé pour contourner la limite d'un appel.

## Voix : disponibilité prouvée

Chatterbox V3 a effectivement synthétisé la phrase française sur CPU Modal, à partir de la référence Noé fournie et autorisée par l'utilisateur. Les poids existants de `pvs-commercial-audio-models` ont été montés en lecture seule. Le résultat est synthétique, pas une prise humaine. La synthèse a pris 53,05 s dans la fonction, hors préparation de l'environnement. Sa durée est 3,68 s. Whisper small local retrouve les mots attendus, WER normalisé 0 ; l'utilisateur a ensuite approuvé la voix et le débit.

L'API officielle accepte `from_local(..., t3_model='v3')`, `language_id='fr'` et `audio_prompt_path`. Le script du dépôt réutilise ces paramètres et ajoute seulement un chemin explicite vers les poids existants. [Source Chatterbox vérifiée](https://github.com/resemble-ai/chatterbox/blob/5de7a54aa4e5e2baadb0182dde554908b48b85c2/src/chatterbox/mtl_tts.py).

VoxCPM2 expose en théorie la référence de timbre et un mode de continuation audio avec transcription. Le wrapper du Studio ne transmet actuellement que `reference_wav_path`, pas le couple `prompt_wav_path`/`prompt_text`. Ses poids sont présents, mais aucune synthèse VoxCPM2 n'a été exécutée ici. Aucun classement qualitatif entre VoxCPM2 et Chatterbox n'est démontré. [Documentation officielle VoxCPM2](https://github.com/OpenBMB/VoxCPM#readme).

Le script `scripts/production/human_performance_voice.py` sert à préparer cette voix sur CPU avec les poids déjà disponibles. Il n'installe pas un service vocal permanent. Dans le Studio local, ce WAV peut être importé et validé ; les moteurs locaux restent soumis à leur propre vérification de disponibilité.

Un enregistrement humain autorisé peut être importé directement et devenir la prestation maîtresse. L'intégration LongCat reçoit image, audio et texte : elle ne reçoit pas de vidéo humaine pour copier précisément les gestes et expressions. Ces dimensions restent générées.

## Preuves et décision

- Ancien vrai rendu LongCat à un segment : [run 39839348041](https://github.com/saillardsimon71-del/nouveau-studio/actions/runs/39839348041). Il prouve une génération, pas la qualité du jeu.
- Voix Noé sur CPU : application `ap-oCFePDLzkph1WYamLQuBAa` ; SHA-256 WAV canonique `7f0b0a1aa0d3184833eb7b93cad36330eeb2c4503bd57f8b942a79c18b236ec6`.
- Poids prêts, contrôle CPU : `ap-dCHzD7m5Iz6pvwC94rghOi`.
- Un seul appel diagnostique soumis : `fc-01M5TC5P39ZVJENB5072CYBJF8`, application `ap-I5fchiiedxY0XNd1BGNz4t`. Echec `ModuleNotFoundError: backend`. Modal a redémarré automatiquement les conteneurs en échec ; l'appel puis l'application ont été arrêtés. Aucun second appel n'a été soumis. Le coût des démarrages n'est pas mesuré ici et ne doit pas être annoncé nul.
- Correctif d'empaquetage vérifié dans le conteneur réel sur CPU : `ap-FjzMMSmSOxo9d259qMhKrm`, `backend_import=true`, plans 93/173 images vérifiés. Cela ne prouve pas l'inférence ou la qualité visuelle.
- Tests : `python -m pytest -o addopts='' -q`. Interface : `npm run build`.

La photo de diagnostic est [RDNE Stock project, Pexels 7490973](https://www.pexels.com/photo/a-woman-leaning-on-the-white-wall-7490973/), sous [licence Pexels](https://www.pexels.com/license/). Usage diagnostique privé, aucun témoignage ou soutien commercial attribué au modèle photographié. Les bras croisés limitent le test de gestes.

Conserver l'architecture voix validée -> LongCat. La prochaine décision porte sur la validation de l'animation avec ce WAV conservé, après autorisation distincte d'une nouvelle tentative puisque le budget d'un appel a été utilisé. Il n'existe pas encore de preuve permettant de conclure au cas A ou B, ni de recommander un autre moteur vidéo.

| Dimension | Mesure ou évaluation | Résultat actuel |
|---|---|---|
| Voix française | Texte, durée, écoute | Mots exacts, 3,68 s, approuvée par l'utilisateur |
| Intonations | Ecoute | Approuvées globalement, aucune note /5 inventée |
| Lèvres | MP4 à vitesse réelle et ralenti, consonnes visibles | Non évaluables sans rendu |
| Expressions | Curiosité sur la question, détente sur la réponse | Non évaluables |
| Gestes | Mouvement motivé, absence de sauts et de déformations | Non évaluables |
| Crédibilité globale | Ecoute et visionnage conjoints | Non démontrée |

Grille humaine à remplir sur le futur MP4 : naturel de la voix /5, intonations /5, synchronisation labiale /5, expressions /5, gestuelle /5, crédibilité globale /5, avec timecodes et description des défauts. Les notes restent vides tant que la personne n'a pas évalué la dimension concernée. Un WER nul, une bouche mobile ou des tests logiciels verts ne prouvent pas le naturel.
