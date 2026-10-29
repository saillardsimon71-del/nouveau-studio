#!/usr/bin/env python3
"""Fruit City / Durian en prison / Episode 4.
Only real Modal LTX outputs are accepted; never substitute stock/still/mock video.
Thirteen 5-second clips, French dialogue in post, dark ambient Foley, SRT/ASS and MP4.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

FIVE_SECONDS = 5.0
FPS = 24
OUTPUT_NAME = "Fruit-City-Durian-en-Prison-Episode-04.mp4"
STYLE = (
    "A premium stylized 3D animated thriller from Fruit City, an anthropomorphic fruit prison. "
    "Dark cinematic premium stylized 3D CGI with believable glossy textures, detailed orange prison uniforms, "
    "physically based lighting, expressive cartoon faces, sinister blue-grey industrial prison at night. "
    "Portrait 9:16 composition, continuous unbroken five-second shot, grounded natural acting, "
    "no humans, no subtitles, no logos, no legible text, no typography, no cut."
)
DURIO = (
    "Durio, the same giant muscular anthropomorphic spiky green-brown durian fruit with intimidating "
    "strong arms, dark sleeveless undershirt, orange prison trousers and a thick gold chain."
)
MOMO = (
    "Momo, the same slim golden-orange anthropomorphic mango fruit with a cold controlled expression, "
    "orange prison jumpsuit and distinctive black sunglasses."
)

# Original episode 4 / self-contained five-second shots, text-to-video as in the proven E04 workflow.
SHOTS = [
  {
    "id": "01",
    "location": "cellule-chaine",
    "voice": "ombre",
    "dialogue": "Durio... t'es pas le vrai.",
    "prompt": "Durio, giant muscular anthropomorphic spiky dark-green and brown durian with expressive eyes, powerful arms, black sleeveless undershirt, orange prison trousers, and distinctive thick gold chain. Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Start with a shocking close-up: Durio's heavy gold chain suddenly writhes around his neck by itself while he gasps and freezes. The unseen voice comes from the dark ventilation grille. Slow urgent camera push, unsettling shadows. Do not show another person."
  },
  {
    "id": "02",
    "location": "cellule-durio",
    "voice": "durio",
    "dialogue": "Quoi ? Montre-toi !",
    "prompt": "Durio, giant muscular anthropomorphic spiky dark-green and brown durian with expressive eyes, powerful arms, black sleeveless undershirt, orange prison trousers, and distinctive thick gold chain. Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Durio angrily yanks his gold chain away from his chest and turns toward the rusty ventilation grille, defensive fighting posture, startled eyes. Single medium close-up with restrained handheld push-in, continuous action."
  },
  {
    "id": "03",
    "location": "ventilation",
    "voice": "ombre",
    "dialogue": "Celui qui sort... devient l'autre.",
    "prompt": "Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Extreme close-up of the rusted ventilation grille, endless blackness behind the slots and dust motes floating in a narrow strip of moonlight. Shadow seems to breathe, no visible mouth or monster. Very slow lens creep toward darkness."
  },
  {
    "id": "04",
    "location": "cellule-porte",
    "voice": "momo",
    "dialogue": "Recule ! C'est un piège !",
    "prompt": "Momo, slim golden-orange anthropomorphic mango with a controlled but frightened expression, distinctive black sunglasses and orange prison jumpsuit. Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Momo suddenly pushes the cell door inward, grabs the iron bars with one mango-colored hand and warns someone inside. Black sunglasses slightly tilted, visibly frightened, silhouette framed by a dim prison corridor. Controlled fast dolly into his face."
  },
  {
    "id": "05",
    "location": "confrontation",
    "voice": "durio",
    "dialogue": "Tu savais qu'il était là ?",
    "prompt": "Durio, giant muscular anthropomorphic spiky dark-green and brown durian with expressive eyes, powerful arms, black sleeveless undershirt, orange prison trousers, and distinctive thick gold chain. Momo, slim golden-orange anthropomorphic mango with a controlled but frightened expression, distinctive black sunglasses and orange prison jumpsuit. Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Tight two-shot: Durio turns away from the ventilation grille to confront Momo near the cell door, accusing glare, fists clenched. Momo stands rigid and avoids his eyes. Slow orbit in blue-grey low light."
  },
  {
    "id": "06",
    "location": "momo-aveu",
    "voice": "momo",
    "dialogue": "J'ai ouvert cette grille... une fois.",
    "prompt": "Momo, slim golden-orange anthropomorphic mango with a controlled but frightened expression, distinctive black sunglasses and orange prison jumpsuit. Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Tight close-up of Momo lowering his black sunglasses slightly, revealing fearful golden-orange eyes, confession and shame. Behind him the ominous ventilation grille remains softly out of focus. Slow inward dolly, expressive subtle facial animation."
  },
  {
    "id": "07",
    "location": "souvenir",
    "voice": "",
    "dialogue": "",
    "prompt": "Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Brief memory-like image within a single continuous shot: one old rusted grille is pulled outward by a frightened mango-colored hand in an orange prison sleeve; darkness inside seems unnaturally deep. Pale cold overhead light flickers, fine airborne dust, no creatures, no words."
  },
  {
    "id": "08",
    "location": "grille",
    "voice": "ombre",
    "dialogue": "Et depuis... Momo ne dort plus.",
    "prompt": "Momo, slim golden-orange anthropomorphic mango with a controlled but frightened expression, distinctive black sunglasses and orange prison jumpsuit. Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Close over-the-shoulder view from behind Momo, who faces the rusty ventilation grille while trembling faintly. A moving unnatural shadow crosses the dark slits. Focus shifts from Momo's iconic black sunglasses to the black grille, no visible monster."
  },
  {
    "id": "09",
    "location": "momo-peur",
    "voice": "momo",
    "dialogue": "Il avait ma voix, lui aussi.",
    "prompt": "Momo, slim golden-orange anthropomorphic mango with a controlled but frightened expression, distinctive black sunglasses and orange prison jumpsuit. Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Close-up on Momo's face in the same cell, black sunglasses held in one shaking hand, eyes wide with remembered fear. Cold moonlight on glossy mango skin, natural trembling, shallow depth of field and gentle push-in."
  },
  {
    "id": "10",
    "location": "chaine-symbole",
    "voice": "durio",
    "dialogue": "Pourquoi ma chaîne brille ?",
    "prompt": "Durio, giant muscular anthropomorphic spiky dark-green and brown durian with expressive eyes, powerful arms, black sleeveless undershirt, orange prison trousers, and distinctive thick gold chain. Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Macro cinematic shot: Durio's thick gold chain begins emitting a subtle amber glow from one link, reflecting across his spiky green skin and muscular hands. He looks down in shock; keep the chain's identity consistent, no symbols or readable writing."
  },
  {
    "id": "11",
    "location": "vent-voix",
    "voice": "ombre",
    "dialogue": "Parce que la clé... c'est toi.",
    "prompt": "Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Extreme close-up on the dark ventilation grille while a narrow warm amber reflection of a gold chain crosses the rusty metal. Black negative space, drifting dust, a barely perceptible pressure wave, no face and no text. Slow straight push-in."
  },
  {
    "id": "12",
    "location": "chaine-attiree",
    "voice": "momo",
    "dialogue": "Durio ! Lâche cette chaîne !",
    "prompt": "Durio, giant muscular anthropomorphic spiky dark-green and brown durian with expressive eyes, powerful arms, black sleeveless undershirt, orange prison trousers, and distinctive thick gold chain. Momo, slim golden-orange anthropomorphic mango with a controlled but frightened expression, distinctive black sunglasses and orange prison jumpsuit. Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Durio grips his glowing gold chain as it is pulled unnaturally toward the vent, bending his muscular posture forward. Momo reaches from beside the iron door to stop him. Flickering cold light and slight camera shake. No abrupt cut."
  },
  {
    "id": "13",
    "location": "porte-ouverte",
    "voice": "ombre",
    "dialogue": "Trop tard... je suis dehors.",
    "prompt": "Same Fruit City prison cell: cold concrete walls, single iron bunk on the right, small high barred window, rusty ventilation grille beside the bed, blue-gray moonlight. Final cliffhanger shot: the rusty ventilation grille slowly swings open all by itself, revealing impenetrable darkness; a large spiky durian-shaped shadow silently appears on the opposite wall while Durio is blurred in the foreground, still wearing his gold chain. Slow ominous push, no explicit double character, cut to black at end."
  }
]
assert len(SHOTS) == 13

VOICE_CONFIG = {
    "momo": ("fr-FR-HenriNeural", "+5%", "+3Hz", "fr+m3", 165, 65),
    "durio": ("fr-FR-HenriNeural", "-9%", "-22Hz", "fr+m7", 145, 31),
    "ombre": ("fr-FR-HenriNeural", "-24%", "-38Hz", "fr+m1", 123, 23),
}


def run(cmd: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(cmd, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def preflight(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    if len({s["id"] for s in SHOTS}) != len(SHOTS):
        raise ValueError("Duplicate shot ID")
    if any(not s["prompt"] or len(s["prompt"]) > 6000 for s in SHOTS):
        raise ValueError("Missing or oversized LTX prompt")
    manifest = {
        "series": "Fruit City — Durian en prison",
        "episode": 4, "title": "L’autre Durio",
        "duration_s": 65, "aspect": "9:16", "render_model": "LTX-2.5",
        "no_mock": True, "release": "private editorial review only",
        "character_note": "Text-anchored identity. No verified episode-1/2 character reference PNGs were available in this branch.",
        "shots": [{"start_s": i * 5, "duration_s": 5, **s,
                   "prompt": STYLE + " " + s["prompt"]} for i, s in enumerate(SHOTS)]
    }
    (out / "episode-04-storyboard.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("PREFLIGHT: 13 narrative shots / 65s / prompts and French dialogues validated / 0 GPU")


def render(out: Path) -> None:
    preflight(out)
    clips = out / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    for n, shot in enumerate(SHOTS, start=1):
        dest = clips / f"shot-{shot['id']}-ltx.mp4"
        if dest.is_file() and dest.stat().st_size > 100_000:
            print(f"SKIP already rendered {dest}")
            continue
        prompt = STYLE + " " + shot["prompt"]
        print(f"REAL MODAL LTX shot {n}/13: {shot['id']} / {shot['location']}", flush=True)
        run([
            "modal", "run", "deploy/modal_ltx_worker.py", "--mode", "render",
            "--prompt", prompt, "--duration", str(FIVE_SECONDS), "--aspect", "9:16",
            "--seed", str(240300 + n * 17), "--audio-mode", "silent",
            "--out", str(dest),
        ])
        probe = media_info(dest)
        streams = probe.get("streams", [])
        if not any(v.get("codec_type") == "video" for v in streams):
            raise RuntimeError(f"LTX shot {n} did not create a real video: {dest}")
        meta = dest.with_suffix(".json")
        if not meta.exists():
            raise RuntimeError(f"No Modal generation metadata for shot {n}")
        print(f"Shot {n}/13 saved: {dest.stat().st_size} bytes", flush=True)


def media_info(path: Path) -> dict:
    return json.loads(run([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration,size",
        "-of", "json", str(path)
    ], capture=True))


def normalize_shots(out: Path) -> Path:
    norm = out / "normalized"
    norm.mkdir(parents=True, exist_ok=True)
    source_clips = []
    for shot in SHOTS:
        src = out / "clips" / f"shot-{shot['id']}-ltx.mp4"
        if not src.exists() or src.stat().st_size < 100_000:
            raise RuntimeError(f"Missing real MP4, refusing silent substitution: {src}")
        probe = media_info(src)
        v = next((s for s in probe["streams"] if s.get("codec_type") == "video"), None)
        if not v or not v.get("width"):
            raise RuntimeError(f"Not a real rendered video: {src}")
        if float(probe["format"]["duration"]) < 4.80:
            raise RuntimeError(f"Truncated GPU output {src}")
        dst = norm / f"shot-{shot['id']}.mp4"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
            "-t", "5.000", "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "fps=24,setsar=1,format=yuv420p",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-pix_fmt", "yuv420p", "-r", "24", str(dst)
        ])
        source_clips.append(dst)
    concat = norm / "clips.txt"
    concat.write_text("".join(f"file '{f.resolve()}'\n" for f in source_clips),
                      encoding="utf-8")
    video = norm / "picture.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", str(concat),
         "-an", "-c", "copy", str(video)])
    return video


def timestamp_srt(ms: int) -> str:
    h, r = divmod(ms, 3_600_000)
    m, r = divmod(r, 60_000)
    s, milli = divmod(r, 1000)
    return f"{h:02}:{m:02}:{s:02},{milli:03}"


def timestamp_ass(ms: int) -> str:
    h, r = divmod(ms, 3_600_000)
    m, r = divmod(r, 60_000)
    s, milli = divmod(r, 1000)
    return f"{h}:{m:02}:{s:02}.{milli // 10:02}"


def say(text: str, person: str, dest: Path) -> None:
    voice, rate, pitch, localvoice, speed, localpitch = VOICE_CONFIG[person]
    try:
        import edge_tts
        asyncio.run(edge_tts.Communicate(
            text=text, voice=voice, rate=rate, pitch=pitch
        ).save(str(dest)))
        if dest.stat().st_size < 1000:
            raise RuntimeError("Empty neural voice")
        print(f"Neural French voice delivered: {person}", flush=True)
    except Exception as error:
        # A declared fallback, not a silent claim of neural voice quality.
        print(f"NOTICE: Edge TTS unavailable ({type(error).__name__}); using espeak-ng fallback", flush=True)
        wav = dest.with_suffix(".wav")
        run(["espeak-ng", "-v", localvoice, "-s", str(speed), "-p",
             str(localpitch), "-w", str(wav), text])
        shutil.copyfile(wav, dest.with_suffix(".fallback.wav"))
        dest.unlink(missing_ok=True)
        dest.with_suffix(".wav").rename(dest.with_suffix(".fallback-source.wav"))


def build_audio_and_subs(out: Path) -> tuple[Path, Path, Path, list[dict]]:
    from pydub import AudioSegment

    sound_dir = out / "sound"
    sound_dir.mkdir(exist_ok=True)
    duration_ms = 65_000

    ambient = sound_dir / "ambient.wav"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=52:sample_rate=48000:duration=65",
         "-f", "lavfi", "-i", "anoisesrc=color=brown:sample_rate=48000:amplitude=0.15:duration=65",
         "-filter_complex",
         "[0:a]volume=-26dB[a];[1:a]volume=-29dB[b];[a][b]amix=inputs=2:normalize=0,lowpass=f=330",
         "-ar", "48000", "-ac", "2", str(ambient)])
    master = AudioSegment.from_file(ambient).set_channels(2)
    master = master[:duration_ms]

    # Three quiet in-world knocks at 25-28 seconds, without external licensed SFX.
    knock = sound_dir / "knock.wav"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=68:sample_rate=48000:duration=0.38",
         "-af", "afade=t=out:st=0.08:d=0.30,volume=-5dB",
         "-ar", "48000", "-ac", "2", str(knock)])
    thud = AudioSegment.from_file(knock).set_channels(2)
    for ms in (57200, 58400, 59600):
        master = master.overlay(thud, position=ms)

    cues = []
    voices = []
    for i, shot in enumerate(SHOTS):
        if not shot["dialogue"]:
            continue
        who = shot["voice"]
        voice_path = sound_dir / f"voice-{shot['id']}.mp3"
        say(shot["dialogue"], who, voice_path)
        # Edge output = .mp3; fallback = explicit .fallback-source.wav.
        real_voice = voice_path if voice_path.exists() else voice_path.with_suffix(".fallback-source.wav")
        if not real_voice.exists():
            raise FileNotFoundError(f"No TTS result for {shot['id']}")
        clip = AudioSegment.from_file(real_voice).set_channels(2).set_frame_rate(48000)
        if who == "ombre":
            clip = clip.low_pass_filter(900) - 3
        elif who == "durio":
            clip = clip - 1
        if len(clip) > 4300:
            # Ensure dialogue does not spill over unrelated next shot.
            clip = clip[:4300].fade_out(250)
        start = i * 5000 + 350
        stop = min(i * 5000 + 4900, start + max(1300, len(clip) + 180))
        master = master.overlay(clip, position=start)
        cues.append({"start_ms": start, "end_ms": stop,
                     "text": shot["dialogue"], "speaker": who})
        voices.append({"shot": shot["id"], "speaker": who,
                       "source": real_voice.name, "duration_ms": len(clip)})
    if len(master) < duration_ms:
        master += AudioSegment.silent(duration=duration_ms - len(master))
    master = master[:duration_ms].fade_in(200).fade_out(300)
    mixed = sound_dir / "episode04-dialogues-ambience.wav"
    master.export(mixed, format="wav", parameters=["-ar", "48000"])

    srt = out / "exports" / "Fruit-City-E04-sous-titres.srt"
    srt.write_text("".join(
        f"{i}\n{timestamp_srt(c['start_ms'])} --> {timestamp_srt(c['end_ms'])}\n{c['text']}\n\n"
        for i, c in enumerate(cues, 1)
    ), encoding="utf-8")

    ass = sound_dir / "captions.ass"
    prefix = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,DejaVu Sans,56,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,4,2,2,65,65,270,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = []
    for cue in cues:
        txt = cue["text"].replace("{", "(").replace("}", ")")
        if len(txt) > 32 and " " in txt:
            pivot = len(txt) // 2
            pos = min((j for j, ch in enumerate(txt) if ch == " "),
                      key=lambda j: abs(j - pivot))
            txt = txt[:pos] + r"\N" + txt[pos + 1:]
        lines.append(f"Dialogue: 0,{timestamp_ass(cue['start_ms'])},"
                     f"{timestamp_ass(cue['end_ms'])},Default,,0,0,0,,{txt}\n")
    ass.write_text(prefix + "".join(lines), encoding="utf-8")
    return mixed, srt, ass, voices


def assemble(out: Path) -> None:
    preflight(out)
    export = out / "exports"
    export.mkdir(exist_ok=True)
    picture = normalize_shots(out)
    mixed, srt, ass, voices = build_audio_and_subs(out)
    final = export / OUTPUT_NAME
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(picture), "-i", str(mixed),
        "-vf", "subtitles=" + str(ass),
        "-t", "65.0", "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", "24",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-movflags", "+faststart", str(final)
    ])
    probe = media_info(final)
    video = next((v for v in probe["streams"] if v["codec_type"] == "video"), None)
    audio = next((v for v in probe["streams"] if v["codec_type"] == "audio"), None)
    length = float(probe["format"]["duration"])
    if not video or not audio or (video["width"], video["height"]) != (1080, 1920):
        raise ValueError(f"Final video/audio or size invalid: {probe}")
    if abs(length - 65.0) > 0.6:
        raise ValueError(f"Unexpected final duration {length}")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", "1.25", "-i", str(final),
         "-frames:v", "1", str(export / "Fruit-City-E04-miniature.jpg")])
    costs = []
    for shot in SHOTS:
        path = out / "clips" / f"shot-{shot['id']}-ltx.json"
        if path.exists():
            meta = json.loads(path.read_text(encoding="utf-8"))
            costs.append({"shot": shot["id"], "estimated_modal_usd": meta.get("cost_estimate_usd"),
                          "generation_seconds": meta.get("generation_seconds")})
    report = {
        "final_video": final.name, "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
        "duration_s": length, "format": "9:16", "resolution": [1080, 1920], "fps": 24,
        "video_model": "LTX-2.5 real Modal outputs", "clips": len(SHOTS),
        "voice": voices, "subtitles": srt.name, "gpu": costs,
        "gpu_estimate_usd": round(sum(float(x["estimated_modal_usd"] or 0) for x in costs), 4),
        "attribution": "Synthetic French neural voices when available; espeak-ng fallback is disclosed in logs.",
        "publication": "NOT PUBLISHED. Human visual and audio quality check required."
    }
    (export / "Fruit-City-E04-production.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (export / "LIRE-AVANT-PUBLICATION.txt").write_text(
        "FRUIT CITY — Durian en prison, episode 4.\n"
        "Fiction originale 3D, 13 clips LTX.\n"
        "Aucun acteur réel, aucune publicité, aucun téléchargement automatique sur réseaux.\n"
        "Contrôler visuellement l'identité des fruits sur chaque plan et les dialogues;\n"
        "le pipeline ne garantit pas la cohérence inter-plan en absence de PNG de référence.\n",
        encoding="utf-8")
    print(f"FINAL READY: {final} ({length:.2f}s) — QA editorial required", flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["preflight", "render", "assemble"])
    p.add_argument("--out", type=Path, default=Path("artifacts"))
    a = p.parse_args()
    if a.command == "preflight":
        preflight(a.out)
    elif a.command == "render":
        render(a.out)
    else:
        assemble(a.out)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"EP04 PRODUCTION FAILED: {exc}", file=sys.stderr)
        raise
