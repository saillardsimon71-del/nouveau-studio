import argparse
import json
import re
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import butter, sosfilt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app import graphics, media, qc
from backend.app.engines.assembly import AssemblyEngine, _esc, _srt
from backend.app.engines.base import EngineRequest

W, H, FPS, DURATION = 1080, 1920, 24, 26
IVORY, COPPER = (245, 240, 230), (220, 165, 105)


class Context:
    def log(self, message, **kwargs):
        print(message, flush=True)

    def check_cancelled(self):
        pass


def encode_video(source, output, duration, filters, extra_inputs=None):
    media.run_ffmpeg(["-i", str(source), *(extra_inputs or []), "-filter_complex", filters,
                      "-map", "[v]", "-an", "-t", str(duration), "-r", str(FPS),
                      "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", str(output)])


def make_logo(work, output):
    font = ImageFont.truetype(str(work / "fonts/Manrope-ExtraBold.ttf"), 158)
    im = Image.new("RGBA", (1400, 300))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 50, 220, 250), 38, outline=COPPER, width=8)
    d.line([(65, 205), (65, 108), (167, 108)], fill=IVORY, width=9)
    d.line([(98, 175), (172, 101)], fill=COPPER, width=13)
    d.line([(133, 101), (174, 101), (174, 143)], fill=COPPER, width=11)
    d.text((270, 155), "SiteQuiVend", font=font, fill=IVORY, anchor="lm")
    im.save(output / "logo-sitequivend.png")
    im.resize((900, 193), Image.Resampling.LANCZOS).save(work / "logo-video.png")


def sound_design(work):
    sr = 48000
    rng = np.random.default_rng(8123)
    result = np.zeros((DURATION * sr, 2), dtype=np.float64)
    for k, cut in enumerate([0.05, 4, 8, 12, 13.1, 17, 18, 19, 20, 21]):
        n = int(0.38 * sr)
        t = np.arange(n) / sr
        boom = 0.12 * np.sin(2 * np.pi * (70 * t - 30 * t * t)) * np.exp(-12 * t)
        noise = sosfilt(butter(2, [700, 6500], btype="bandpass", fs=sr, output="sos"), rng.normal(0, 1, n))
        swoosh = noise * np.exp(-((t - 0.09) / 0.06) ** 2) * 0.045
        tick = 0.022 * (np.sin(2 * np.pi * 1180 * t) + 0.4 * np.sin(2 * np.pi * 1770 * t)) * np.exp(-22 * t)
        mono = boom + swoosh + tick
        start = max(0, int((cut - 0.07) * sr))
        size = min(n, len(result) - start)
        pan = 0.1 * (-1) ** k
        result[start:start + size, 0] += mono[:size] * (1 + pan)
        result[start:start + size, 1] += mono[:size] * (1 - pan)
    with wave.open(str(work / "sound-design.wav"), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes((np.clip(result, -1, 1) * 32767).astype("<i2").tobytes())


def make_mix(work):
    sound_design(work)
    names = ["produit", "restaurant", "villa", "interieur"]
    args = ["-i", str(work / "vo-master.wav"), "-ss", "46", "-i", str(work / "ascension.mp3"),
            "-i", str(work / "sound-design.wav")]
    for name in names:
        args += ["-i", str(work / f"{name}-ltx.mp4")]
    filters = [
        "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voice][side]",
        "[1:a]atrim=duration=26,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
        "loudnorm=I=-22:TP=-7:LRA=8,aresample=48000,afade=t=in:d=0.35,afade=t=out:st=24.4:d=1.6[music]",
        "[music][side]sidechaincompress=threshold=0.035:ratio=4:attack=12:release=280:makeup=1[duck]",
        "[2:a]volume=0.7[fx]",
    ]
    for i, (start, length) in enumerate([(0, 4), (4, 4), (8, 4), (12, 5)]):
        filters.append(f"[{i+3}:a]atrim=duration={length},asetpts=PTS-STARTPTS,"
                       f"aformat=sample_rates=48000:channel_layouts=stereo,volume=0.035,"
                       f"afade=t=in:d=0.08,afade=t=out:st={length-0.15}:d=0.15,"
                       f"adelay={start*1000}:all=1[n{i}]")
    filters.append("[voice][duck][fx][n0][n1][n2][n3]amix=inputs=7:normalize=0:duration=longest,"
                   "apad=whole_dur=26,atrim=duration=26,alimiter=limit=0.94:level=false[mix]")
    media.run_ffmpeg([*args, "-filter_complex", ";".join(filters), "-map", "[mix]", "-ar", "48000",
                      "-c:a", "pcm_s24le", str(work / "mix-master.wav")])


def prepare_segments(work):
    prepared = work / "prepared"
    prepared.mkdir(exist_ok=True)
    geom = "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1,fps=24"
    definitions = [("produit", 0, 4, 0), ("restaurant", 4, 4, 0), ("villa", 8, 4, 0),
                   ("comparison", 12, 5, 0), ("produit", 17, 1, 1.3), ("restaurant", 18, 1, 1.3),
                   ("villa", 19, 1, 1.5), ("interieur", 20, 1, 2), ("endcard", 21, 5, 0)]
    clips = []
    for index, (name, start, length, source_start) in enumerate(definitions):
        visual = prepared / f"visual-{index}.mp4"
        if name == "comparison":
            filters = (f"[0:v]{geom},setpts=PTS-STARTPTS[a];[1:v]{geom},setpts=PTS-STARTPTS[b];"
                       "[a][b]blend=all_expr='if(lt(T,0.75),A,if(gt(T,1.6),B,"
                       "if(lt(X,W*(T-0.75)/0.85),B,A)))'[v]")
            encode_video(work / "source-interieur-5s.mp4", visual, length, filters,
                         ["-i", str(work / "interieur-ltx.mp4")])
        elif name == "endcard":
            filters = (f"[0:v]{geom},gblur=sigma=18,drawbox=x=0:y=0:w=iw:h=ih:color=0x0b1115@0.78:t=fill[bg];"
                       "[1:v]format=rgba,fade=t=in:st=0.15:d=0.45:alpha=1[logo];"
                       "[bg][logo]overlay=x=90:y=680:shortest=1[v]")
            encode_video(work / "produit-ltx.mp4", visual, length, filters,
                         ["-loop", "1", "-i", str(work / "logo-video.png")])
        else:
            filters = f"[0:v]trim=start={source_start}:duration={length},setpts=PTS-STARTPTS,{geom}[v]"
            encode_video(work / f"{name}-ltx.mp4", visual, length, filters)
        with_audio = prepared / f"clip-{index}.mp4"
        media.run_ffmpeg(["-i", str(visual), "-ss", str(start), "-i", str(work / "mix-master.wav"),
                          "-map", "0:v", "-map", "1:a", "-t", str(length), "-c:v", "copy",
                          "-c:a", "aac", "-b:a", "256k", str(with_audio)])
        clips.append({"path": str(with_audio), "duration_s": length, "kind": name})
        print(f"Préparé : {name} ({start}-{start+length}s)", flush=True)
    return clips


def direction_events():
    items = []
    def title(start, end, text, x, y, size=80, colour=None, alignment=7, spacing=0):
        tags = rf"\an{alignment}\pos({x},{y})\fs{size}\fsp{spacing}\fad(120,120)"
        if colour:
            tags += rf"\c{colour}"
        items.append((graphics.Event(start, end, text, "Heading", 2), tags))
    title(0.08, 3.9, "PUBLICITÉS IA POUR ENTREPRISES", 90, 110, 24, spacing=2)
    title(0.05, 3.9, "Votre activité", 90, 210, 85)
    title(0.05, 3.9, "mérite mieux.", 90, 325, 92, "&H0069A5DC&")
    title(0.25, 3.9, "qu'une vidéo ordinaire.", 94, 450, 40)
    title(4.05, 7.9, "RESTAURATION", 90, 110, 24, spacing=3)
    title(4.1, 7.9, "Donnez envie.", 90, 230, 84)
    title(8.05, 11.9, "IMMOBILIER", 90, 110, 24, spacing=3)
    title(8.1, 11.9, "Changez de\ndimension.", 90, 230, 82)
    title(12.05, 16.9, "VOTRE VIDÉO. RÉINVENTÉE.", 90, 110, 29, spacing=1)
    title(12.05, 12.8, "AVANT", 90, 180, 48)
    title(13.6, 16.9, "APRÈS", 90, 180, 48, "&H0069A5DC&")
    title(13.6, 16.9, "TRANSFORMATION CRÉATIVE PAR IA", 90, 255, 23)
    for start, text in [(17, "UNE IMAGE"), (18, "VOTRE UNIVERS"), (19, "UNE VIDÉO"), (20, "VOTRE PUBLICITÉ")]:
        title(start + 0.04, start + 0.96, text, 540, 280, 54, alignment=8, spacing=2)
    title(21.2, 25.9, "UNE SEULE SIGNATURE.", 540, 570, 25, alignment=8, spacing=3)
    title(21.45, 25.9, "CRÉATION VIDÉO PAR IA", 540, 945, 29, alignment=8, spacing=2)
    title(21.7, 25.9, "Parlons de votre projet.", 540, 1120, 49, "&H0069A5DC&", alignment=8)
    title(21.3, 26, "Démonstration créative. Visuels et voix générés par IA.", 540, 1615, 22, alignment=8)
    title(21.3, 26, "Musique : Ascension - Scott Buckley (CC BY 4.0)", 540, 1670, 19, alignment=8)
    title(21.3, 26, "Voix : Kokoro / SIWIS (Apache 2.0 / CC BY 4.0)", 540, 1705, 18, alignment=8)
    return items


def captions(work):
    align = json.loads((work / "voice-asr-aligned.json").read_text(encoding="utf-8"))
    phrases = [
        ["Votre activité mérite mieux", "qu'une vidéo ordinaire.", "Un produit, une table, un lieu."],
        ["Et soudain, une autre dimension.", "Votre idée, vos photos, vos vidéos,", "nous les transformons",
         "en publicités", "qui captent l'attention."],
        ["Création, voix, montage.", "Une seule signature.", "SiteQuiVend.", "Parlons de votre projet."],
    ]
    events = []
    def normalise(text):
        token = re.sub(r"[^\w']", "", text.lower().replace("’", "'"))
        return "publicités" if token == "publicité" else token
    for paragraph, wanted in zip(align, phrases):
        words = []
        for word in [w.copy() for s in paragraph["segments"] for w in s.get("words", [])]:
            word["word"] = word["word"].strip().replace("’", "'")
            if word["word"].startswith("'") and words:
                words[-1]["word"] += word["word"]
                words[-1]["end"] = word["end"]
            else:
                words.append(word)
        i = 0
        while i < len(words) - 2:
            if [normalise(w["word"]) for w in words[i:i+3]] == ["site", "qui", "vend"]:
                words[i:i+3] = [{"word": "SiteQuiVend.", "start": words[i]["start"], "end": words[i+2]["end"]}]
            i += 1
        cursor = 0
        for phrase in wanted:
            tokens = phrase.split()
            group = words[cursor:cursor+len(tokens)]
            if [normalise(w["word"]) for w in group] != [normalise(w) for w in tokens]:
                raise ValueError(f"Alignement vocal à vérifier : {phrase} / {group}")
            events.append(graphics.Event(group[0]["start"], group[-1]["end"] + 0.10, phrase, "Subtitle", 4))
            cursor += len(tokens)
        if cursor != len(words):
            raise ValueError("Des mots de la voix ne sont pas couverts par les sous-titres")
    for current, following in zip(events, events[1:]):
        current.end = min(current.end, following.start - 0.015)
    return events


def write_ass(path, items, subtitle_events):
    heading = graphics.AssStyle("Heading", font="Manrope", size=80, primary="&H00E6F0F5", bold=1,
                                outline=0, shadow=0, alignment=7, margin_l=90, margin_r=90, margin_v=90)
    subtitle = graphics.AssStyle("Subtitle", font="Manrope", size=45, bold=1, margin_l=90, margin_r=90,
                                 margin_v=360, outline=2.1, shadow=1.1, alignment=2)
    events = [x[0] for x in items] + list(subtitle_events)
    graphics.build_ass(events, path, W, H, styles=[heading, subtitle])
    tags = [x[1] for x in items] + [r"\fad(70,90)"] * len(subtitle_events)
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    for n, line in enumerate(lines):
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            parts[9] = "{" + tags[i] + "}" + parts[9]
            lines[n] = ",".join(parts)
            i += 1
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def thumbnail(work, output):
    im = Image.open(work / "produit-reference.png").convert("RGB")
    ratio = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * ratio), round(im.height * ratio)), Image.Resampling.LANCZOS)
    x, y = (im.width-W)//2, (im.height-H)//2
    im = im.crop((x, y, x+W, y+H)).convert("RGBA")
    logo = Image.open(output / "logo-sitequivend.png").resize((770, 165), Image.Resampling.LANCZOS)
    im.alpha_composite(logo, (62, 64))
    d = ImageDraw.Draw(im)
    def text(x, y, value, size, colour):
        d.text((x, y), value, font=ImageFont.truetype(str(work / "fonts/Manrope-ExtraBold.ttf"), size), fill=colour)
    text(78, 282, "Votre activité", 82, IVORY)
    text(78, 390, "mérite mieux.", 93, COPPER)
    text(82, 235, "PUBLICITÉS IA POUR ENTREPRISES", 29, IVORY)
    im.convert("RGB").save(output / "SiteQuiVend-miniature.jpg", quality=96, subsampling=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--post-only", action="store_true")
    args = parser.parse_args()
    work, output = args.work.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    make_logo(work, output)
    base = work / "assembly/export_9x16.mp4"
    if not args.post_only:
        make_mix(work)
        clips = prepare_segments(work)
        result = AssemblyEngine().run(EngineRequest(kind="assembly", output_dir=work / "assembly",
            project={"name": "SiteQuiVend", "format": "9:16"}, inputs={"clips": clips},
            params={"fps": FPS, "subtitles": False, "transitions": False, "shot_labels": False,
                    "loudness_target": -14.0}), Context())
        (work / "assembly-manifest.json").write_text(json.dumps({"duration_s": DURATION, "clips": clips,
            "assembly": result.diagnostics}, ensure_ascii=False, indent=2), encoding="utf-8")
    cue_events = captions(work)
    items = direction_events()
    for subtitled in [False, True]:
        ass = work / ("publicite-sous-titres.ass" if subtitled else "publicite-sans-sous-titres.ass")
        write_ass(ass, items, cue_events if subtitled else [])
        out = output / ("SiteQuiVend-publicite-26s.mp4" if subtitled else "SiteQuiVend-sans-sous-titres.mp4")
        media.run_ffmpeg(["-i", str(base), "-vf", f"subtitles=filename='{_esc(ass)}':fontsdir='{_esc(work/'fonts')}'",
                          "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-profile:v", "high",
                          "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
                          "-metadata", "title=SiteQuiVend - Votre activité mérite mieux",
                          "-metadata", "comment=Visuels et voix générés avec IA. Démonstration créative.", str(out)])
        report = qc.inspect_export(out, {"format": "9:16", "fps": FPS}, expected_duration_s=DURATION)
        out.with_suffix(".qc.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"EXPORT {out}: QC={report['verdict']}", flush=True)
    (output / "SiteQuiVend-sous-titres.srt").write_text(_srt(cue_events), encoding="utf-8")
    thumbnail(work, output)


if __name__ == "__main__":
    main()
