# MiniMax H3 officiel dans nouveau-studio — 25 octobre 2026

## État réel

- LTX-2.5 et LongCat restent inchangés.
- MiniMax H3 n'était pas installé / intégré dans la branche principale avant cette intervention.
- Un adaptateur **API officielle MiniMax** et son GitHub Actions sont maintenant ajoutés.
- **Aucun checkpoint H3 n'est installé sur Modal.** Aucun GPU H3 n'a été loué. Aucun rendu H3 n'a été demandé.
- La branche de préparation a passé des tests **0 appel API / 0 GPU / 0 $**.

## Pourquoi ne pas auto-héberger H3 sur Modal immédiatement ?

La licence officielle MiniMax H3 Community License, article I « Excluded Territories »,
exclut l'UE (dont la France), le Royaume-Uni, les États-Unis et la Corée du Sud.
Une autorisation explicite est nécessaire pour déployer les poids depuis un territoire exclu.
L'utilisation d'un serveur aux États-Unis ne change pas la portée de la licence accordée à l'utilisateur européen.

Sources officielles :
- Licence : https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE
- Formulaire de licence : https://platform.minimax.io/h3-license
- API hébergée : https://platform.minimax.io/docs/api-reference/video-generation-v2-create
- Consultation des tâches : https://platform.minimax.io/docs/api-reference/video-generation-v2-query

## Lancer un test officiel MiniMax H3 via GitHub Actions

1. Dans https://platform.minimax.io, choisir le mode **Pay-as-you-go API** et créer une clé.
2. Dans GitHub > Settings > Secrets and variables > Actions,
   créer le secret de dépôt **MINIMAX_API_KEY**. Ne jamais ajouter cette valeur dans le code.
3. Actions > « MiniMax H3 | Official API (no self-hosted weights) » > Run workflow.
4. Sélectionner `stage=preflight` pour une vérification sans dépense.
5. Pour une **vraie génération payante** seulement : `stage=render`, `confirm_spend=oui`.
   Fournir un prompt de 5 s pour un seul plan et une `image_url` HTTPS publique
   vers une **photo authentique** de mannequin/vêtement (Pexels, droits vérifiés).
   Ne pas fournir une image générée par IA : c'est la contrainte du portfolio.
6. Par défaut `MiniMax-H3`, `768P`, `5` s, `9:16`. Avec une image initiale,
   le ratio est automatiquement hérité de la photo.
7. En cas de succès, le MP4 et le JSON de métadonnées sont dans **Artifacts** du run ;
   **vérifier humainement visage, vêtements, membres, mouvement et droits avant publication**.

Tarifs publics affichés sur la plateforme : MiniMax H3 768P : environ
**0,08 USD/seconde** de sortie ; 2K : environ **0,13 USD/seconde**, auxquels
peuvent s'ajouter d'autres éléments de facturation selon les entrées.
Ce ne sont pas des dépenses engagées.
Source : https://platform.minimax.io/subscribe/token-plan?tab=api-enterprise

## Limites connues

- Ni identité d'un mannequin ni fidélité textile ne sont garanties par l'API.
- Aucune clé MiniMax n'a été lue ou configurée par ce changement.
- Aucune vidéo H3 n'a encore été générée et validée.
- Pas de génération en lot automatique : **une validation visuelle à chaque plan**.
- Si le compte dispose d'une **autorisation écrite H3 d'auto-hébergement dans l'UE**,
  on pourra envisager une installation Modal distincte avec son propre volume,
  sans affecter LTX-2.5. Il faut alors mesurer VRAM, coût GPU et durée de chargement
  avant le premier poids téléchargé.
