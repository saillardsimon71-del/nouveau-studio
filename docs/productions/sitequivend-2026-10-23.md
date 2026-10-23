# SiteQuiVend - Votre activité mérite mieux

Publicité vitrine terminée le 23 octobre 2026. Durée : 26 secondes. Format vertical 9:16, 1080x1920, H.264 avec audio AAC stéréo à 48 kHz. Une version sous-titrée et une version sans sous-titres incrustés sont fournies. Les deux conservent la signature, les mentions IA et les crédits.

## Fichiers

- `SiteQuiVend-publicite-26s.mp4` : version destinée aux réseaux sociaux.
- `SiteQuiVend-sans-sous-titres.mp4` : même film sans les sous-titres de la voix.
- `SiteQuiVend-miniature.jpg` : miniature verticale, 1080x1920.
- `SiteQuiVend-sous-titres.srt` : sous-titres séparés et synchronisés.
- `logo-sitequivend.png` : signature transparente créée en postproduction.
- `Texte-de-publication.txt` : légende et crédits à conserver, notamment pour la musique.
- `Production-et-metriques.json` et `Consommation-Modal.json` : provenance, paramètres, mesures et coûts.
- `Sources/` : vidéo d'entrée de la transformation, sortie native correspondante et métadonnées.

## Construction du film

| Temps | Contenu |
| --- | --- |
| 0-4 s | Hook immédiat et flacon ambré en photographie publicitaire |
| 4-8 s | Dessert gastronomique en travelling macro |
| 8-12 s | Villa et piscine au crépuscule |
| 12-17 s | Vidéo d'intérieur source, balayage avant/après, transformation IA |
| 17-21 s | Montage rythmé des univers présentés |
| 21-26 s | Signature SiteQuiVend et appel à parler de son projet |

Les scènes illustrent des possibilités créatives. Elles ne sont pas présentées comme des réalisations clients, des biens à vendre ou des résultats commerciaux mesurés.

## Moteurs réellement utilisés

Quatre prises vidéo ont été calculées avec LTX-2.5 Distilled INT8-convrot, dans le ComfyUI Modal déjà validé. Trois prises utilisent une image de départ originale pour conserver l'apparence du produit, du dessert et de la villa. La quatrième encode les 121 images d'une vidéo source dans le VAE, puis effectue une transformation video-to-video par dénaturation partielle. L'avant/après ne repose pas sur une simple photographie animée ou un filtre colorimétrique.

Les poids LTX existants ont été réutilisés en lecture seule. Aucun téléchargement répété, aucune modification des volumes de l'ancien Studio IA et aucune relance GPU n'ont été nécessaires. Temps cumulés dans les fonctions vidéo : 440,523 secondes.

La voix française a été synthétisée sur CPU avec Kokoro-82M, voix `ff_siwis`, sous licence Apache 2.0. Sa source vocale SIWIS est créditée sous CC BY 4.0. Le texte a été contrôlé par transcription locale Whisper puis aligné par mots. Les apostrophes, le pluriel de "publicités" et l'orthographe SiteQuiVend ont été corrigés dans les sous-titres.

Le montage utilise `AssemblyEngine`, `graphics.build_ass` et le contrôle qualité existants du dépôt. La signature, les textes et les sous-titres ont été composés en postproduction avec Manrope, sous SIL Open Font License. La musique est un extrait de [Ascension, par Scott Buckley](https://www.scottbuckley.com.au/library/ascension/), sous CC BY 4.0, complété par du sound design original et les ambiances LTX atténuées.

## Mesures et revue

- Deux exports lisibles de 26,00 secondes, 1080x1920, pixels carrés, profil H.264 High.
- Cadence nominale 24 fps ; 623 images vidéo mesurées, avec une durée de conteneur incluant l'audio de 26,00 secondes.
- Audio AAC stéréo, 48 kHz ; niveau intégré -14,7 LUFS ; crête vraie -1,4 dBTP.
- Aucun segment noir ni gel détecté, confirmé par une passe ffmpeg séparée.
- Sous-titres relus, 12 séquences sans chevauchement, placées à distance des bords et des crédits.
- Contrôle visuel des prises et des exports : aucun visage à stabiliser, aucun texte généré dans les scènes, aucun watermark de fournisseur ni défaut géométrique évident sur les prises sélectionnées.

Cette version peut servir de film vitrine auprès de prospects : les univers sont immédiatement identifiables, la transformation est montrée, la marque et la proposition de service sont lisibles avec ou sans le son.

Limites : les plans LTX ont été produits en 768x1344 puis mis à l'échelle pour la livraison 1080x1920. La transformation d'intérieur réinterprète certains détails du mobilier. Elle doit rester présentée comme une création illustrative, pas comme un relevé architectural fidèle d'un bien réel.

## Coût

Consommation Modal relevée pour les deux applications de cette production : **0,39089376 USD**, soit environ **0,39 USD**.

| Ressource | USD |
| --- | ---: |
| L40S | 0,26443492 |
| CPU | 0,05514886 |
| Mémoire | 0,07054835 |
| Transferts | 0,00076163 |
| Total Modal | 0,39089376 |

Les images préparatoires utilisent le quota de l'outil imagegen ; leur prix unitaire n'est pas fourni par l'outil et n'est pas inclus dans ce montant. Le montage et la vérification locale sur CPU ne sont pas valorisés financièrement. Aucun conteneur Modal de cette production ne reste actif.

## Sources et publication

La vidéo source est [Elegant Modern Living Room with Natural Light, par Alef Morais](https://www.pexels.com/video/elegant-modern-living-room-with-natural-light-37479012/), utilisée selon la [licence Pexels](https://www.pexels.com/license/), qui permet les modifications et la création de publicités. La musique nécessite de conserver les crédits indiqués dans le texte de publication ; les crédits sont aussi présents à l'écran.

Kokoro : [modèle Apache 2.0](https://huggingface.co/hexgrad/Kokoro-82M). SIWIS : [base et licence](https://datashare.ed.ac.uk/handle/10283/2353). Manrope : licence jointe dans `Licences/`.

LTX-2.5 relève des [conditions communautaires LTX-2.x](https://github.com/Lightricks/LTX-2/blob/main/LICENSE-2_x), qui prévoient notamment une licence payante pour les structures atteignant 10 millions de dollars de chiffre d'affaires annuel. Les paramètres et les révisions exactes des modèles sont conservés dans les métadonnées de production.
