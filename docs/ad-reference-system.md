# Références publicitaires dans Studio IA

Version 1, 25 octobre 2026. Entrée principale :
`python scripts/ad_references.py --help`.

## Audit du dépôt

Audit effectué sur `996776d95ccdeb6cfc07bbbd5c7e07681b9d2d2e`, après clonage réel.

| Composant existant | Constat et réutilisation |
|---|---|
| `backend/app/director.py` | Un Director, endpoint chat compatible OpenAI, JSON Pydantic, une réparation, repli heuristique. Le template local ne traitait que l'automatisation. Enrichissement ajouté à cette fonction, sans agent ni service supplémentaire. |
| `schemas.py`, `api.py` | Proposition puis application du storyboard. Ajout de `use_references`, `ad_category`, performance, provenance et personnage par plan. |
| `jobs.py` | SQLite et pool de threads, contrat `EngineRequest`. Les nouveaux plans H3 conservent la photo du personnage dans les entrées vidéo. |
| `engines/modal_remote.py` | `ModalH3Engine` joint audio/vidéo, contrat texte commun à LTX. Il reste inchangé. Le chemin avatar antérieur appelle TTS puis LongCat, limité à 3,72 s. |
| `deploy/modal_h3_worker.py` | ComfyUI, `MiniMaxH3ImageToVideo`, prompt texte de 7000 caractères maximum, plans 4..15 s à 24 fps. Aucun champ SSML, vitesse TTS ou acteur structuré n'est exposé : les consignes sont du texte naturel. |
| `scripts/production/sitequivend_audio.py` | Whisper CPU, timestamps par mot, comparaison au texte attendu. La nouvelle analyse reprend cette bibliothèque et ses options, en exigeant un checkpoint local et sans amorcer l'ASR avec le dialogue attendu. Le script de production reste intact. |
| `media.py`, `graphics.py`, `engines/assembly.py` | PyAV, FFmpeg, SRT/ASS, montage, loudness, noir et gel. Réutilisation du probe, du lanceur FFmpeg et de la checklist QC. Aucun second moteur de montage. |
| `db.py`, `config.py` | Projets, plans, personnages, artefacts et JSON `shots.params` dans SQLite WAL ; fichiers dans `data/`. La provenance utilise ces colonnes, sans migration. |
| Analyse vidéo | Pas de service général de compréhension visuelle. Le Qwen3-VL empaqueté avec H3 est un encodeur du moteur, pas un endpoint d'analyse réutilisable tel quel. |
| Tests / Actions | 81 tests initiaux. Un faux `modal` global polluait la suite ; isolation corrigée dans le test H3. Les huit workflows existants restent inchangés. Nouveau workflow exclusivement CPU sur PR. |

Les films MAISON / 01 et ÉCLAT / 01 ne sont pas présents dans ce checkout.
Le MP4 `demo_simulation_vertical.mp4` est une simulation et ne constitue pas une
référence professionnelle ni une preuve de qualité H3.

## Données et recherche

`studio/ad-references/catalog/` contient 15 fiches JSON, réparties 5/3/3/2/2.
Voir [le catalogue](../studio/ad-references/catalog/README.md) et
[les sources et licences](datasets-and-rights.md).

Toutes ces campagnes sont **documentées uniquement par leurs pages sources**.
Aucun fichier de marque n'a été téléchargé, aucune voix ou expression de ces
15 films n'a été mesurée. Les durées, formats et dialogues inconnus restent `null`.
Le groupe UGC/présentation comprend surtout des présentateurs professionnels ;
la forme face caméra de la candidature IL MAKIAGE doit être confirmée visuellement.
Il ne s'agit pas d'un corpus de cinq témoignages UGC authentifiés.

Les cinq recettes `source_description` sont des synthèses documentaires
provisoires. Chaque règle renvoie à une observation et une source. Elles inspirent
la structure et les démonstrations, sans prétendre décrire un jeu d'acteur observé.
L'import de médias autorisés permet de produire des recettes `analyzed_media`,
prioritaires dans la recherche. Les données et annotations des benchmarks externes
ne sont pas importées.

Le schéma Pydantic est l'autorité ; ses exports JSON Schema sont dans `schemas/`.
Une observation précise sa base (`source_description`, `video_observation`,
`acoustic_measurement`, `model_inference`), sa confiance, son localisateur et ses
incertitudes. Les observations média imposent des timestamps ; l'import dans une
analyse vérifie également le SHA-256 du média et la durée. La confiance d'un
annotateur reste déclarative, sans calibration statistique implicite.

## Analyse CPU d'un fichier autorisé

Installer les dépendances usuelles du backend ; pour ASR et prosodie seulement :

```powershell
python -m pip install -r backend/requirements-ad-analysis.txt
python scripts/ad_references.py analyze C:/medias/notre-publicite.mp4 --out data/ad-references/analysis/notre-pub --authorized-use "Production agence autorisée" --whisper-model C:/modeles/whisper/base.pt
```

Le checkpoint doit déjà exister. Aucun poids, dataset ou média n'est téléchargé
par la commande. La V1 borne chaque analyse à 10 minutes, exporte au plus
80 images intermédiaires et reste locale. Une déclaration d'autorisation est
obligatoire ; elle est enregistrée, sans constituer une validation juridique.

Sans ASR, la présence de parole reste inconnue. Une piste musicale n'est pas une
preuve de parole. Sans piste audio, la parole est absente. Une transcription
Whisper ou WhisperX déjà disponible peut être passée avec
`--transcript transcription.json` au lieu de `--whisper-model`. Elle reste
`supplied_transcript_unverified` et son débit n'alimente pas les recettes mesurées.

Les changements de plans proviennent du score `scene` de FFmpeg (seuil 0,3).
Les fondus, flashs et mouvements de caméra peuvent produire des erreurs ; les
frontières sont des candidats, pas une classification validée des transitions.
Les timestamps, durées et images médianes permettent le contrôle.

La voix fournit nombre de mots, temps couvert par les segments ASR, mots/minute
sur le clip et sur ces segments, couverture des timestamps par mot, temps
d'articulation si complet, pauses entre segments et phrases ponctuées, et débit
par segment. Le temps ASR inclut des pauses internes : il n'est pas une mesure
VAD du temps phoné. Les chevauchements temporels sont fusionnés pour éviter de
compter deux fois le temps. Aucun diariseur n'est installé.

`--speech-only` doit être réservé à une piste de parole isolée. Cette déclaration
active pYIN de librosa, sur les segments ASR, entre 60 et 500 Hz : F0, dispersion
en demi-tons, tendances montantes/descendantes et contour RMS en dBFS. Sans cette
déclaration, le RMS concerne le mix et les mesures vocales de hauteur restent
absentes. Musique, voix superposées et erreurs d'octave limitent l'interprétation.
Les candidats d'emphase énergétique ne prouvent ni intention, ni émotion.
Respiration, accent et ton communicatif demandent une écoute ou une annotation.

L'analyse visuelle sémantique n'est pas automatisée dans cette V1 : pas de score
inventé pour regard, visage, gestes, produit, mouvement de caméra ou continuité.
Les images permettent une annotation humaine ; un futur endpoint multimodal peut
produire le même format `Observation`. Importer une liste avec `--observations`
après validation contre `schemas/observation.schema.json` ; distinguer observation
directe et inférence. Les assertions marketing, hook, promesse, preuve, objection
et CTA peuvent être annotés dans le domaine `marketing`, avec leurs timestamps.

## Import et réutilisation

```powershell
python scripts/ad_references.py import data/ad-references/analysis/notre-pub/analysis.json --reference-id agence_001 --category ugc_presenter --brand "Notre agence" --title "Notre publicité"
python scripts/ad_references.py catalog --brief "UGC cosmétique française"
```

Par défaut, les imports sont privés dans `PVS_DATA_DIR/ad-references` et complètent
le catalogue versionné. Ils ne copient ni ne publient le MP4. `PVS_AD_REFERENCE_DIR`
remplace complètement la bibliothèque pour une installation spécifique.
`--library-dir` permet de cibler ce dossier lors de l'import. Un identifiant
existant est refusé. La recette automatique décrit uniquement les mesures et
observations disponibles ; elle ne transforme pas une inférence émotionnelle
en fait. Relire ses règles avant de généraliser à d'autres produits.

## Director et H3

L'API existante accepte :

```json
{
  "brief": "UGC cosmétique, présentatrice française, sérum, 20 secondes",
  "use_llm": false,
  "use_references": true,
  "ad_category": "ugc_presenter"
}
```

Le mode est désactivé par défaut. Sans catégorie reconnue, catalogue disponible
ou JSON valide, le Director existant continue ; une erreur de bibliothèque est
signalée dans `notes`. La recherche locale sélectionne une recette et trois
références maximum, avec un budget de 6000 caractères, sans transcription.
Le mode LLM reçoit ce contexte avant le scénario. Son transport est testé avec
un faux endpoint local ; aucun appel LLM payant n'a été exécuté pour la mission.

Le mode local étend les templates par catégorie : quatre plans, 16..48 secondes.
Il ne prétend pas rédiger librement chaque brief. Le brief produit reste dans
les prompts et les allégations sont limitées ; les choix et formulations
doivent être relus pour le produit réel. Les modèles H3 ne sont pas exécutés.

Les nouveaux plans parlés sont des jobs **vidéo H3 avec son natif**. Les conserver
en `avatar` les aurait dirigés vers TTS/LongCat. Le changement est limité aux
propositions enrichies ; les parcours antérieurs restent inchangés. Le personnage
A sélectionné et sa photo sont conservés. Pour un second personnage B, fournir sa
photo/une photo de scène adaptée avec `params.reference_image` lors d'un futur
rendu ; cette mission n'en lance aucun. Le frontend n'ajoute pas de bouton dédié :
l'activation se fait par l'API ou le CLI.

Chaque prompt précise locuteur, accent français, timbre, intention, rythme,
pauses, emphase, réactions et coordination voix/visage. Pour les récits, le LLM
doit fournir `performance.speaker_role` A/B par plan parlé ; aucun locuteur n'est
deviné à partir de l'ordre des plans. Une seule voix parle par plan.

Les débits 165 mots/minute (présentation) et 150 (récit) et la réserve de pause
de 0,4 s sont des **règles éditoriales**, pas des statistiques des 15 références.
Un débit ASR local réellement disponible peut guider la cible, bornée à 120..190
par règle éditoriale. Un texte trop long ou un plan hors 4..15 s est refusé avec
une erreur explicite, sans accélération forcée. Cette estimation ne garantit
pas que H3 respectera la consigne. L'évaluation de la sortie reste nécessaire.

## Démonstrations sans génération

```powershell
python scripts/ad_references.py demos --out studio/ad-references/demos
```

| Brief de 20 s | Recette et références | Contribution vérifiable |
|---|---|---|
| UGC cosmétique, présentatrice française | `presenter_documentary_v1`, ad_001, ad_004, ad_005 | Offre simple, démonstration, étape suivante ; voix française et rythme sont éditoriaux. |
| Manteau en laine haut de gamme | `fashion_documentary_v1`, ad_009, ad_010, ad_011 | Vêtement constant, geste d'usage, mouvement mesuré ; pas de reproduction des scènes originales. |
| Cadeau et deux personnages | `story_documentary_v1`, ad_012, ad_013 | Situation partagée, points de vue, réaction ; dialogues A/B originaux, tours séparés. |

Les trois fichiers `demos/*.json` contiennent les briefs, références, recette,
provenance par décision et **prompts complets réellement générés localement**.
Leur champ `video_generated` vaut `false`.

## Évaluation et comparaison

```powershell
python scripts/ad_references.py evaluate data/ad-references/analysis/eclat-old/analysis.json --scene-id eclat_01 --version old --expected-dialogue "Dialogue attendu" --out data/ad-references/evaluations/eclat-old.json
python scripts/ad_references.py compare data/ad-references/evaluations/eclat-old.json data/ad-references/evaluations/eclat-new.json --out data/ad-references/evaluations/eclat-comparison.json
```

L'évaluation indique WER, parole, débit, pauses, hauteur, nombre et durée des plans.
La comparaison exige la même scène et le même schéma ; elle ne calcule des écarts
qu'avec la même configuration d'analyse (modèle ASR et son hash, librairies,
seuil, langue, périmètre audio). Changer le texte attendu est signalé. Les scores
manquants restent `null`. Une valeur plus grande ne désigne pas un meilleur film.
Les contrôles humains de lip-sync, naturel, continuité, produit et défauts restent
`pending`, avec emplacement pour la preuve. Aucun score audio ne les valide.

`evaluations/eclat_01-comparison.json` prépare les deux versions sans résultats
inventés. Il faudra analyser les fichiers existants lorsqu'ils seront disponibles.
Aucune régénération n'est nécessaire pour mesurer l'ancienne version.

## Vérifications exécutées et limites

La suite couvre catalogue et droits, JSON invalide/absent, contexte borné,
transcriptions incomplètes, chevauchements, timestamps invalides, fichiers muets,
musique sans ASR, cuts réels, F0 contrôlée, import, API, casting et conservation
de photo. Un défaut préexistant d'isolation du faux Modal a été corrigé.
Commande exécutée dans `.venv` : `python -m pytest -o addopts='' -q`,
résultat : **112 tests réussis**, sans saut, en 48,29 s. Compilation Python et
`git diff --check` réussis. FastAPI 0.162.0, Pydantic 2.14.1 et pytest 9.1.1
respectent les dépendances déclarées du dépôt.

Un test local de 9,023 s avec texte original synthétisé par Microsoft Hortense
(CPU Windows) a réellement exécuté Whisper `base` en cache et librosa : 17 mots,
WER 0, débit sur segments ASR 150,44 mots/minute, médiane F0 218,18 Hz, dispersion
5,61 demi-tons. Ce signal synthétique valide le fonctionnement technique,
**pas le naturel d'un acteur ni la qualité d'une publicité professionnelle**.
Le rapport compact est dans `evaluations/cpu-validation.json` ; le média et les
contours détaillés restent dans `data/`, hors Git.

Aucun benchmark externe installé, aucune vidéo de marque analysée intégralement,
aucune compréhension multimodale ou diarisation exécutée, aucun poids H3 modifié,
aucun rendu H3/LTX, aucune modification de SiteQuiVend.fr. L'amélioration visuelle
et vocale réelle de la future ÉCLAT reste à vérifier sur les sorties de production.
