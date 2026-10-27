# Arena AI — Photorealistic English talking-head video (2026-10-27)

## Mission
Produce one **real generated MP4**, depicting the person shown in the creator-provided reference portrait looking into camera and speaking a new 45–60 second English professional introduction. The creator states that this is their own portrait and supplied voice sample. `voice.mp3` is a **voice-reference sample only**, not dialogue and not the final soundtrack. First synthesize a 5–8 second sample of the new script using the reference voice, and require human listening/comparison before any video GPU render. Only proceed to the full narration and avatar after that approval. Target is a believable self-recorded talking-head video, with no obvious animation, identity drift, uncanny facial movement or mouth/voice mismatch.

**Do not modify the production engine, deploy infrastructure, or unrelated code merely to improve this one asset.** Audit the current engine and use an already working, proven route. Do not claim successful rendering without a downloadable playable MP4 and a verified QC report.

## Source files (verified and committed to this production branch)
- `assets/portrait.jpg`: creator-provided original JPEG, **123777 bytes**; Git blob SHA `7a027e76012449546f3c8f41348512fb17af10aa`.
- `assets/voice.mp3`: creator-provided original MP3, **204318 bytes**, **11.729 seconds**; Git blob SHA `2159c910f30db2afe8b640d83b08d7c39cacb823`.
- Both media files are **already available** in this branch under `content/productions/english-talking-head-20261027/assets/`. Their Git blob hashes have been checked against the original uploaded files. **Use them directly; do not substitute reference media.**
- **Privacy notice:** this repository is public. The creator explicitly asked for these two media files to be placed here after being informed of public visibility. Do not expose additional personal assets or generated results without permission.

## New spoken copy and voice
Write a new, natural first-person English professional introduction of 45–60 seconds (roughly 95–125 words). Do not claim personal credentials, clients, results, or biographical facts that the creator has not supplied. The workflow's current draft script is in `.github/workflows/modal-avatar.yml`; revise it only to improve natural spoken delivery or fit the measured duration.

Use the original MP3 **only as a voice-cloning reference**. Reuse the repository's Chatterbox Multilingual V3 voice engine in English, and produce an initial 5–8 second sample of the new dialogue. A person must listen to the generated sample and compare it directly with the original reference before approving any avatar-video GPU run. Do not claim voice fidelity from model choice, logs, or automated measurements. After approval, generate the full 45–60 second speech with the same model/reference; use that generated WAV as LongCat conditioning and remux that exact synthesized track into the final video. No TTS-provider substitution or unapproved voice claims.

## Performance & image direction
- Front-facing natural camera presentation, direct eye contact, calm confident manner, restrained friendly expression, **minimal natural head movement**, blinks, subtle breathing.
- Preserve face shape, complexion, eyes, hair, natural skin texture, light-blue shirt and neutral grey background. No face beautification, stylization, de-aging, artificial teeth, facial warping or teeth flicker.
- Soft even photographic lighting, normal lens perspective, natural depth of field; no camera pans/zooms, no B-roll, transitions, music, subtitles, logos or on-screen typography.
- Begin with the source pose; the voice drives articulations. Neutral mouth / rest during gaps. Preserve real pausing/emphasis, lip consonants, jaw transitions; avoid smiles sustained throughout.
- Deliver 1:1 master matching the square source when that best preserves quality. A 9:16 crop is optional only if anatomy and composition remain natural; no stretching. Prefer natural talking-head realism over aesthetic overproduction.

## Execution procedure for Arena AI
1. Use the existing GitHub Actions → Modal path and audit its tested LongCat route. The 3.72 s pilot is the only documented avatar duration; longer segmented output remains experimental and requires review.
2. Verify original asset hashes before use. Use `voice.mp3` as the reference sample only; create the new spoken script in English.
3. Run the `voice_sample` workflow stage to synthesize a representative 5–8 second excerpt via Chatterbox Multilingual V3 in English. Upload the sample artifact and stop.
4. A human must listen to that sample alongside the supplied voice reference and make an explicit approval decision. If similarity/naturalness is unsuitable, do not run video GPU. Do not infer voice fidelity from automated tests.
5. Only after approval and explicit GPU-spend authorization, synthesize the complete script from the same voice reference, verify it is 45–60 seconds, then call LongCat with the original portrait and generated WAV. For long audio use the documented segment continuation flags; inspect for continuity defects.
6. Remux the exact synthesized WAV used for conditioning, then produce one H.264/AAC MP4. Deliver it with synthesis/video run identifiers, measured cost, automated QC, and human review of voice likeness, identity, lip-sync, and temporal artifacts.
7. If the result is not convincing, report precisely what failed. Do not claim realistic identity, lip-sync, or voice likeness from automated checks alone.

## Rules
- Create only production-specific files and logs in this dedicated branch. Leave `main` and existing production workflows untouched.
- No public publishing or outreach. No unnecessary API calls, GPU preparation, or irreversible actions.
- The original MP3 is a voice sample, not dialogue. Do not use a synthetic lookalike portrait or expose generated media outside the private workflow artifacts.
