# Portfolio SiteQuiVend — films morph

Deux films premium verticaux (Food & Luxe 27,6 s, Automotive & Lifestyle 26,7 s)
construits sur des plaques photographiques, une caméra virtuelle 2.5D et des
transitions morph. Tout tourne sur CPU : aucun GPU, aucune modification de
l'ancien Studio IA.

Documentation complète : [`docs/PORTFOLIO_MORPH.md`](../../docs/PORTFOLIO_MORPH.md).
Rapport de la production livrée :
[`docs/productions/sitequivend-portfolio-morph-2026-10-23.md`](../../docs/productions/sitequivend-portfolio-morph-2026-10-23.md).

## Commandes utiles

```bash
export PYTHONPATH=.

python -m scripts.portfolio.build --film both --debug-circles   # ancres de morph
python -m scripts.portfolio.build --film both --sheets           # planches-contact
python -m scripts.portfolio.build --film food --full             # rendu complet
python -m scripts.portfolio.build --film auto --finish           # son/cover/QC seuls
python -m scripts.portfolio.ltx_shots --film both --dry-run      # plan LTX + coût
python -m pytest tests/test_portfolio_morphfilm.py -q            # 23 tests, CPU
```

## Où sont les médias

`data/portfolio-2026-10-23/` (ignoré par Git, sauf `data/exports/`) :

- `food/`, `auto/` — plaques sources et plaque dérivée ;
- `build/` — rendus image intermédiaires (sans audio) ;
- `audio/` — scores WAV ;
- `exports/` — **livrables finaux** (MP4, covers, QC, JSON) ;
- `debug/` — images de vérification des ancres, géométries, planches.

Les plaques ne sont pas versionnées : `derive.py` reconstruit la plaque « jante
auto » depuis la jante « food », mais les six images sources doivent être
regénérées avec les prompts conservés dans `exports/*.json` (`prompts`).
