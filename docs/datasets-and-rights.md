# Sources, outils et droits

Vérification du 25 octobre 2026 : README, fichiers de licence et dépendances
accessibles, métadonnées GitHub `pushed_at`. Les dates ci-dessous attestent une
activité du dépôt, pas une garantie de maintenance. Le relevé brut compact est
dans `studio/ad-references/research/repository-status-2026-10-25.json`.

| Projet | Fonctionnement, dépendances et activité constatés | Droits et décision V1 |
|---|---|---|
| [AdsQA](https://github.com/TsinghuaC3I/AdsQA) | 1544 films, 10962 clips, cinq tâches : concepts visuels, émotion, thèmes, persuasion, audience. URLs et QA séparés ; ReAd-R utilise EasyR1/Python 3.10. Dernier push 2025-10-30. | Pas de licence de dépôt reconnue par GitHub. Le README exclut la redistribution des vidéos originales. Retenir la distinction concept/émotion/preuve, sans importer données ni entraînement. |
| [Ads-1k](https://github.com/yunlong10/Ads-1k) | Annotations d'importance et cohérence ; 942 films d'entraînement, 99 de test décrits ; features BERT, Swin et VGGish, pickles préextraits. Dernier push 2023-04-14. | BSD-2-Clause au niveau dépôt, sans établir les droits des publicités tierces. Retenir importance du plan et cohérence de la succession ; pas de téléchargement des features ou médias. |
| [Video Persuasion](https://github.com/midas-research/video-persuasion) | 1002 vidéos, annotations multistratégies et lien Drive. Douze catégories ; pas de pipeline déployable nécessaire. Dernier push 2023-10-23. | Licence de réutilisation non établie. Référencer la taxonomie et la publication, pas importer le dataset. |
| [AdShot](https://github.com/ostadabbas/AdShot) | 823 paires 30/15 s, frontières et correspondance entre plans, 18 labels. Extraction/candidatures et pipeline Qwen, dépendances lourdes séparées. Dernier push 2026-10-13. | Annotations CC BY-NC 4.0, médias dérivés sous accès contrôlé et accord de recherche académique non commerciale. **Aucune donnée AdShot intégrée**, y compris CSV/frames/audio. Seul le problème de sélection sous budget de durée informe la conception. |
| [MG-VAU](https://github.com/Reforged-Labs/mg-vau) | 13 publicités, 13 tâches, 65 critères binaires ; labels structurés et évaluations humaines. Exemple évaluateur Python 3.13+. Dernier push 2026-04-06. | Texte de licence CC BY 4.0 pour le dataset ; le README distingue les films de tiers, conservant leurs droits. Retenir l'évaluation par critère et par preuve. Aucun film ni label importé. |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | `detect(path, ContentDetector())`, détecteurs adaptatif et fondu ; OpenCV/NumPy, FFmpeg pour découpage, PyAV optionnel. Version PyPI vérifiée 0.7.2 ; dernier push 2026-10-25. | BSD-3-Clause. Utile si détection avancée nécessaire ; non installé car FFmpeg déjà présent suffit aux candidats de cuts V1. |
| [WhisperX](https://github.com/m-bain/whisperX) | ASR faster-whisper/CTranslate2, alignement, diarisation optionnelle. `pyproject` main 3.8.7rc1 : Python 3.10..3.13, torch ~2.8, torchvision ~0.23, pyannote, transformers. Dernier push 2026-10-22. | BSD-2-Clause pour le code ; modèles annexes et accès HF à vérifier séparément. Ne pas remplacer la pile torch de production. Import du JSON aligné supporté ; réutilisation de Whisper déjà employé dans le dépôt pour l'ASR CPU effectif. |
| [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) | Compréhension multimodale image/vidéo, timestamps et description. README : transformers >=4.57, qwen-vl-utils, torch ; vLLM/accélération optionnels. Dernier push 2026-01-30. | Code Apache-2.0 ; vérifier la carte du checkpoint choisi avant déploiement. Aucun service général déjà disponible dans Studio ; l'encodeur H3 n'en est pas un. Préparer les images et importer des observations validées, sans nouvel hébergement GPU. |
| [librosa](https://github.com/librosa/librosa) | Analyse du signal, NumPy/SciPy/Numba, soundfile, scikit-learn. Version stable installée et testée 0.11.0 ; dernier push 2026-10-06. | ISC. Retenu pour pYIN et RMS de parole isolée. Pas de détection de tempo musical utilisée comme débit de parole. |
| [LivePortrait](https://github.com/KlingAIResearch/LivePortrait) | Le lien KwaiVGI redirige vers KlingAIResearch. Transfert de mouvements, stitching et retargeting ; Python 3.10, torch, ONNX Runtime GPU, transformers 4.38 dans requirements. Dernier push 2026-06-01. | Code MIT ; la licence précise que les modèles InsightFace fournis sont réservés à la recherche non commerciale et doivent être remplacés pour un usage commercial. Pas d'intégration : aucune nécessité démontrée et aucun besoin de moteur supplémentaire en V1. |

Les douze stratégies de Video Persuasion sont : identité sociale, concrétude,
ancrage/comparaison, dépassement de la réactance, réciprocité, pied-dans-la-porte,
autorité, impact social, anthropomorphisme, rareté, preuve sociale, indéterminé.
Ce sont des étiquettes de lecture, pas des preuves d'efficacité. Elles peuvent
être inscrites dans `Observation.value` du domaine `marketing`, accompagnées
de la scène, de la confiance et de l'incertitude ; aucune attribution n'est
automatiquement ajoutée à une publicité non visionnée.

## Catalogue des campagnes

Les 15 sources se trouvent dans [catalog/README.md](../studio/ad-references/catalog/README.md).
Les fiches résument les pages web et n'en reproduisent pas les transcriptions.
Une page de marque, un upload public, un palmarès ou une fiche d'archive n'accorde
pas de licence de reproduction, d'entraînement commercial ou de republication.
Les fichiers restent chez les ayants droit ; on conserve URL, provenance et
métadonnées originales. Aucune protection ni condition d'accès n'a été contournée.
Les mesures de campagnes publiées par les sources ne sont pas importées comme
résultats commerciaux validés ni extrapolées aux productions SiteQuiVend.

Pour un import client, conserver l'autorisation et son périmètre (analyse,
stockage, personnes filmées, musique, diffusion éventuelle). Le système exige
une déclaration opérateur et conserve le fichier local ; il ne déduit jamais
de cette autorisation un droit de redistribuer les médias. Les analyses privées
et fichiers MP4 restent dans `data/`, ignoré par Git.
