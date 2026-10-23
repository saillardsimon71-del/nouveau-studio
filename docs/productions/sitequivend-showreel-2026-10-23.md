# SiteQuiVend portfolio - production du 23 octobre 2026

Brief : film commercial de 30 secondes, 1080x1920, 48 fps, pour le portfolio de SiteQuiVend.fr. Six secteurs et six actions produit réelles, issus exclusivement de photographies Pexels. Aucun visuel imagegen.

## Direction

"Made to be desired" : le désir passe par la matière et le geste. Ivoire, espresso, cuir tabac, graphite et or. Lumière latérale chaude, textures lisibles, noirs contrôlés. La progression va des liquides aux objets : goutte, extraction, nappage, cuir manipulé, téléphone tourné, pendentif en mouvement.

Les différences de luminosité servent le montage : beauté claire en ouverture, café plus dense, dessert riche en texture, mode sombre, tech graphite et bijou doré. La signature reprend le site consulté le 23 octobre : fond #0b0d0c, ivoire #f0efe8 et accent #d6f36a, signe graphique et nom SiteQuiVend.

## Fabrication

- Worker existant `deploy/modal_ltx_worker.py`, poids existants en lecture seule, L40S, une génération à la fois, aucune relance automatique.
- Paramètres, sources, photographes et prompts : `scripts/production/sitequivend_showreel.json`.
- Sélection initiale : 21 photos examinées ; six retenues pour leur composition et une action directement réalisable à partir de l'état photographié.
- Six prises de six secondes pour disposer de poignées de montage. Estimation de génération plafonnée à 2 USD dans le script, puis contrôle de la facturation réelle.
- Examen des prises avant montage ; sélection et éventuel rejet consignés dans le dossier de livraison.
- RIFE 4.6 déjà présent localement : 24 vers 48 fps, uniquement à l'intérieur d'une prise, jamais entre deux coupes.
- Montage ffmpeg, réutilisation des fonctions media et QC du studio. Recadrage fixe, étalonnage léger, coupes franches, aucune animation numérique de photographie.

## Audio et diffusion

Priorité au son des gestes. Aucun morceau généré ajouté par défaut. Les sons natifs doivent être sélectionnés, nettoyés et montés avec les actions ; aucune qualité d'écoute humaine ne sera revendiquée sans écoute effective. La décision de mix et les limites seront consignées dans le rapport final.

Le film représente une création portfolio du studio, sans prétendre que les produits photographiés sont des clients ou que les marques montrées recommandent SiteQuiVend. Les liens Pexels et les crédits sont conservés. La licence Pexels consultée autorise modification et usage publicitaire : https://www.pexels.com/license/.

## Livraison attendue

Master MP4, MP4 web 48 fps avec démarrage progressif, cover verticale, rapport des sources/coûts/limites, métadonnées de contrôle et ZIP. Une intégration HTML locale est fournie pour faciliter la mise en ligne.

## Résultat vérifié

Livraison locale : `outputs/SiteQuiVend-Portfolio/` et `outputs/SiteQuiVend-Portfolio-30s.zip`.

- Deux MP4 de 30,00 secondes, 1080x1920, 48 fps, 1440 images entièrement décodées chacun, AAC stéréo 48 kHz, démarrage progressif vérifié.
- Six univers, quatorze plans montés et une carte finale de trois secondes. Sept prises générées, dont une reprise macro skincare ; son début avec goutte trop grosse est exclu.
- Audio : sons produit natifs, sans musique. Gain global mesuré et corrigé : -18,1 LUFS, -5,0 dBTP.
- Contrôle de la chronologie à quatre images par seconde, puis sept images consécutives par coupe. Aucun noir, gel ni pic isolé de luminance dans les prises retenues. Carte fixe finale intentionnelle. Pas d'écoute humaine ni de visionnage humain à vitesse réelle revendiqués.
- Coût Modal relevé : 0,72953510 USD. 877,714 secondes cumulées dans les fonctions de génération. Aucun conteneur de cette production encore actif.
- Références Pexels : Vie Studio 8148742, Amelia Hallsworth 5461667, Kübra Doğu 8774282, Berna 19354498, Luis Quintero 13570135 et Maryam 13292930. Liens et empreintes dans le manifeste et la livraison.

Les images natives 768x1344 à 24 fps ont été agrandies ; le 48 fps est calculé par RIFE dans chaque prise. Les recadrages macro sont moins définis que des sources natives 1080p. La rotation du pendentif est plus ample que demandé. Le ZIP contient les rapports, licences, références, prompts et preuves d'interpolation. Son intégrité et les empreintes des fichiers ont été vérifiées. Le site n'a pas été déployé.

## Recette

Le dossier de travail attend `references/<id-pexels>.jpg`, les trois polices Manrope de la livraison dans `fonts/`, et `edit.json` copié depuis `scripts/production/sitequivend_showreel_edit.json`.

1. `sitequivend_showreel_shots.py --work <dossier>` réutilise le worker LTX, une prise à la fois, sans retry et avec plafond d'estimation. Ne pas l'exécuter pour simplement consulter les livrables : il engage des calculs Modal si les prises n'existent pas.
2. `sitequivend_showreel_interpolate.py <prises-mp4> --rife <installation-rife>` réutilise RIFE 4.6 local.
3. `sitequivend_showreel_assemble.py --work <dossier> --output <livraison>` construit les deux exports et les covers.
4. `sitequivend_showreel_review.py <mp4> --output <planches>` et `sitequivend_showreel_verify.py <mp4> --output <controle> --edit <dossier>/edit-final.json` reproduisent les contrôles de livraison.

Ces scripts sont des recettes de cette production. Aucun changement dans le moteur, l'API ou l'interface du studio.
