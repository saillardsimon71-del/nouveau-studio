# Arena AI — Photorealistic English talking-head video (2026-10-27)

## Mission
Produce one **real generated MP4**, depicting the person shown in the creator-provided reference portrait looking into camera and speaking **exactly the supplied English audio**. The person states that this is their own portrait; the creator supplied the voice sample. Target is a believable self-recorded talking-head video, with no obvious animation, identity drift, uncanny facial movement or mouth/voice mismatch.

**Do not modify the production engine, deploy infrastructure, or unrelated code merely to improve this one asset.** Audit the current engine and use an already working, proven route. Do not claim successful rendering without a downloadable playable MP4 and a verified QC report.

## Source files (required, NOT COMMITTED)
- `assets/portrait.jpg`: source provided by creator, 1600 x 1600 JPEG.
- `assets/voice.mp3`: source provided by creator, mono MP3 44.1 kHz/128 kbps, **11.729 seconds**.
- These two private media files exist in the originating ChatGPT conversation **but are not yet available in this Git branch**. They must be supplied via an appropriate private channel before rendering. **Do not silently substitute any other image or audio.**
- Repository is currently **public**: do not commit portrait, voice, any derived face/voice media or generated output to this public repository without the creator expressly accepting public disclosure. Prefer a secure private asset store or a private repository, with expiring signed URLs and no credentials in logs.

## Exact spoken copy
> Not louder. Not faster. Just better. Crafted for the ones who notice the difference between good and unforgettable. This is for you.

Use the exact supplied voice track as the final audio. **No TTS, re-recording, cloning or voice replacement.** Non-destructive technical resampling is allowed for model ingestion, then remux original audio for delivery if sync is retained.

## Performance & image direction
- Front-facing natural camera presentation, direct eye contact, calm confident manner, restrained friendly expression, **minimal natural head movement**, blinks, subtle breathing.
- Preserve face shape, complexion, eyes, hair, natural skin texture, light-blue shirt and neutral grey background. No face beautification, stylization, de-aging, artificial teeth, facial warping or teeth flicker.
- Soft even photographic lighting, normal lens perspective, natural depth of field; no camera pans/zooms, no B-roll, transitions, music, subtitles, logos or on-screen typography.
- Begin with the source pose; the voice drives articulations. Neutral mouth / rest during gaps. Preserve real pausing/emphasis, lip consonants, jaw transitions; avoid smiles sustained throughout.
- Deliver 1:1 master matching the square source when that best preserves quality. A 9:16 crop is optional only if anatomy and composition remain natural; no stretching. Prefer natural talking-head realism over aesthetic overproduction.

## Execution procedure for Arena AI
1. Inspect the latest repository branches and **actual tested** speaking-avatar solutions (LongCat + any newer approved-audio or image-to-video route). The published LongCat pilot is only proven for **3.72 s segments**; a 11.729 s result is **not** yet proven.
2. Ensure reference media have been received privately and check hashes, dimensions, exact duration. If not, mark `BLOCKED_MISSING_MEDIA` and stop; do not render a stand-in.
3. Check whether one continuous 11.729 s voice-driven generation is **really** supported. If not, split at real phonetic pauses, retain the original full audio timeline, render overlapping short segments and join without visual jumps or audio discontinuities. Avoid new infrastructure unless strictly necessary.
4. Render one **cheap 2-3 s lip-sync pilot** on a representative, lip-intensive phrase, listen and inspect face/mouth at normal speed. If unsuitable, stop GPU spending and report defect; avoid endless model tweaking.
5. Upon pilot acceptance, render the complete 11.729 s clip, preserving identity/pose/voice, and produce a single standard H.264/AAC MP4.
6. Deliver playable MP4 in an accessible **private** artifact location; provide source ref + exact generation run id + measured cost + automated QC (duration, fps, codec, sound, black/frozen frames) and explicit human QC for identity, lip-sync, temporal artifacts.
7. If quality is below realistic self-shot footage, report precisely what failed. Do not claim indistinguishable realism from automated tests alone.

## Rules
- Create only production-specific files and logs in this dedicated branch. Leave `main` and existing production workflows untouched.
- No public publishing or outreach. No unnecessary API calls, GPU preparation, or irreversible actions.
- Do not alter dialogue or replace the supplied reference with a synthetic lookalike.
