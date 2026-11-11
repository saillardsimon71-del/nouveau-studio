# SiteQuiVend — 13 s premium e-commerce showreel (Pexels + LTX)

**Goal:** a high-quality portfolio demonstration, not another 30-second narrative film.
This GitHub-only production reuses the existing LTX-2.5 Modal worker. No Work quota.
The script + workflow are in this branch, **not** an already rendered/final approved MP4.

## Direction — 13 seconds, 3 real photographed scenes

| Timeline | Source Pexels | Directing |
| --- | --- | --- |
| 0.0–3.6 s | Amber unbranded skincare bottle (Ksenia Chernaya, photo 8054400) | Refined micro-slider movement, stable glass, sunlit highlights |
| 3.6–7.2 s | Chocolate brownies (Roberto Muñoz, photo 15850680) | Film-like macro push-in, tiny believable motion in existing ganache |
| 7.2–10.8 s | Espresso pouring (dino Trex, photo 30678777) | Natural movement in existing espresso stream |
| 10.8–13.0 s | Original SiteQuiVend end card | "AI VIDEO ADS FOR BRANDS" + sitequivend.fr |

**Editing:** only clean hard cuts, no optical morphs, auto transitions, strobe or crossfades. Each clip is LTX image-to-video from a real Pexels image, 768×1344 source at native 24fps. Controlled motion interpolation to 48fps is applied **before** 1080×1920 upscale; interpolation is never described as native generation. Final file ~13 seconds.

**Audio:** a licensed excerpt from *Ascension* by Scott Buckley, **CC BY 4.0**, as used in the successful first SiteQuiVend advert. **Required attribution when publishing:** "'Ascension' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au". The music is not AI-generated or an unidentified sample.

Pexels photography used with its [license](https://www.pexels.com/license/). Photographers and exact source pages are embedded in the exported \`CREDITS.txt\` and \`source-provenance.json\`. The demo must not misrepresent the stills as original photography taken by SiteQuiVend, or imply endorsement by any brand or photographer.

## GitHub workflow

[Actions → SiteQuiVend | Pexels x LTX 13s showreel](../../actions/workflows/sitequivend-showreel-pexels.yml)

1. Pushing the scripts/workflow to this specific branch runs only **Pexels source/music preflight**. No GPU, no billing. Artifact \`SiteQuiVend-Pexels-references\` contains the three reference PNGs.
2. **Review these images before spending GPU**; a photograph with visible brand marks, bad crop or unstable composition must be replaced first.
3. Only then use **Run workflow** on this branch with \`stage: render\` AND \`confirm_spend: oui\`. The GitHub-stored Modal secrets are consumed only on the runner. The workflow calls the existing \`deploy/modal_ltx_worker.py\` on app \`pvs-ltx\` and model volume \`studio-ltx25-models\`.
4. Three independent 5s clips render, with no automatic retries. The artifact \`SiteQuiVend-LTX-source-shots\` preserves them even if montage fails.
5. Final artifact \`SiteQuiVend-Showreel-13s-LTX\` contains MP4, cover, QC/provenance JSON and legal credits.

**GPU cost:** Not yet measured. Earlier 4 clip SiteQuiVend ad cost $0.3909. This 3-shot job should be of the same order if successful, but this is *an estimate*, not a billing cap or price guarantee. Do not start other jobs concurrently. Three calls / no retry and an 8min per-call worker timeout bound accidental consumption, though workspace-level usage must still be checked on Modal.

**Acceptance criteria:** no deformed product/food, no label hallucination, no strobing, no jitter or interpolation ghosts. Visual approval of every shot and edit is necessary before publishing to the portfolio. An Actions green check only means the code ran and container/codec checks passed. If visual quality is not sufficient, reject the output rather than sell it as a premium film.

## Source assets

- [Ksenia Chernaya — amber dropper bottle](https://www.pexels.com/photo/clear-brown-glass-bottle-with-liquid-8054400/)
- [Roberto Muñoz — brownies](https://www.pexels.com/photo/close-up-of-delicious-chocolate-cake-with-fudge-15850680/)
- [dino Trex — coffee extraction](https://www.pexels.com/photo/close-up-of-espresso-pouring-into-cup-30678777/)
- [Scott Buckley — Ascension](https://www.scottbuckley.com.au/library/ascension/) (CC BY 4.0)

No content from the older failed Food and Automotive V1/V2 films is reused. No changes to the main studio engine, old Studio IA, SiteQuiVend site, or DNS.
