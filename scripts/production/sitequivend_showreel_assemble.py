import argparse
import json
import sys
import wave
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app import media

INK = "#0b0d0c"
IVORY = "#f0efe8"
ACCENT = "#d6f36a"


def assets(work):
    scale = 2
    image = Image.new("RGB", (1080 * scale, 1920 * scale), INK)
    draw = ImageDraw.Draw(image)

    def text(y, label, size, color=IVORY, weight="Medium"):
        font = ImageFont.truetype(str(work / "fonts" / f"Manrope-{weight}.ttf"), size * scale)
        draw.text((540 * scale, y * scale), label, font=font, fill=color, anchor="mm")

    def point(x, y):
        return ((x * 3.5 + 466) * scale, (y * 3.5 + 526) * scale)

    draw.polygon([point(x, y) for x, y in [(8.5, 27.8), (19.8, 8.5), (23.6, 14.9), (15.5, 28.7), (8.5, 28.7)]], fill=IVORY)
    draw.polygon([point(x, y) for x, y in [(20.7, 33.5), (31.9, 14), (35.6, 20.6), (28.3, 33.5)]], fill="#90958c")
    center = point(32.7, 8.9)
    radius = 3.1 * 3.5 * scale
    draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), fill=ACCENT)
    text(780, "SiteQuiVend.", 94, weight="ExtraBold")
    text(884, "AI CREATIVE STUDIO", 24, "#a0a49a", "Bold")
    draw.line((498 * scale, 996 * scale, 582 * scale, 996 * scale), fill=ACCENT, width=3 * scale)
    text(1100, "AI Video Ads", 47, weight="Bold")
    text(1169, "for E-commerce Brands", 35)
    text(1530, "sitequivend.fr", 30, "#b8b9ae")
    image.resize((1080, 1920), Image.Resampling.LANCZOS).save(work / "end-card.png")


def cover(final, work, output):
    selected = {}
    with av.open(str(final)) as container:
        for index, frame in enumerate(container.decode(video=0)):
            if index in (110, 310, 510, 1090):
                selected[index] = frame.to_image()
            if index > 1090:
                break
    image = Image.new("RGB", (1080, 1920), INK)
    for i, frame in enumerate(selected.values()):
        panel = ImageOps.fit(frame, (536, 572), centering=(.5, .72))
        image.paste(panel, ((i % 2) * 544, (i // 2) * 580))
    draw = ImageDraw.Draw(image)
    bold = ImageFont.truetype(str(work / "fonts/Manrope-ExtraBold.ttf"), 53)
    medium = ImageFont.truetype(str(work / "fonts/Manrope-Medium.ttf"), 25)
    serif = ImageFont.truetype("C:/Windows/Fonts/pala.ttf", 103)
    draw.text((76, 1235), "SiteQuiVend.", font=bold, fill=IVORY)
    draw.line((76, 1353, 160, 1353), fill=ACCENT, width=3)
    draw.multiline_text((76, 1410), "Made to be\ndesired.", font=serif, fill=IVORY, spacing=4)
    draw.text((76, 1775), "AI VIDEO ADS / E-COMMERCE / 30 SEC", font=medium, fill="#b8b9ae")
    image.save(output / "SiteQuiVend-Showreel-Cover.jpg", quality=94, subsampling=0)
    image.save(output / "SiteQuiVend-Showreel-Cover.webp", quality=90, method=6)


def build(work, output):
    edit = json.loads((work / "edit.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    edit_folder = work / "edit"
    edit_folder.mkdir(exist_ok=True)
    assets(work)
    parts = []
    cursor = 0
    for i, shot in enumerate(edit["shots"]):
        source = work / (shot["source"] + "-ltx-48.mp4")
        a, b = shot["in_frame"], shot["out_frame"]
        dest = edit_folder / f"{i:02}.mp4"
        parts.append(dest)
        shot.update(start_frame=cursor, end_frame=cursor + b - a)
        cursor += b - a
        if dest.exists():
            continue
        crop = shot.get("crop", [0, 0, 1, 1])
        x, y, width, height = crop
        vf = (f"trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS,"
              f"crop=trunc(iw*{width}/2)*2:trunc(ih*{height}/2)*2:trunc(iw*{x}/2)*2:trunc(ih*{y}/2)*2,"
              "crop=trunc(ih*9/32)*2:ih,scale=1080:1920:flags=lanczos,setsar=1,"
              + shot.get("grade", "eq=contrast=1.035:saturation=0.94:brightness=-0.003"))
        media.run_ffmpeg(["-i", str(source), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast",
                          "-crf", "16", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", str(dest)])
        print("EDIT", i, shot["source"], b - a, "frames", flush=True)
    assert cursor == 1296, f"27 seconds of footage required, got {cursor} frames"
    card = edit_folder / "end-card.mp4"
    if not card.exists():
        media.run_ffmpeg(["-loop", "1", "-framerate", "48", "-i", str(work / "end-card.png"), "-t", "3",
                          "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", str(card)])
    parts.append(card)
    listing = edit_folder / "concat.txt"
    listing.write_text("\n".join("file '" + p.resolve().as_posix() + "'" for p in parts), encoding="utf-8")
    video = edit_folder / "picture-master.mp4"
    media.run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(video)])

    groups = []
    for shot in edit["shots"]:
        if groups and groups[-1]["source"] == shot["source"] and groups[-1]["out_frame"] == shot["in_frame"]:
            groups[-1]["out_frame"] = shot["out_frame"]
        else:
            groups.append(dict(shot))
    sound = []
    for i, group in enumerate(groups):
        a, b = group["in_frame"], group["out_frame"]
        length = (b - a) * 1000
        wav = edit_folder / f"sound-{i}.wav"
        target = group.get("audio_lufs", -24)
        duration = (b - a) / 48
        af = (f"atrim=start={a / 48}:end={b / 48},asetpts=PTS-STARTPTS,"
              f"aresample=48000,aformat=channel_layouts=stereo,highpass=f=75,lowpass=f=13000,"
              f"loudnorm=I={target}:TP=-4:LRA=8,aresample=48000,"
              f"afade=t=in:d=0.012,afade=t=out:st={duration - .025}:d=0.025,"
              f"apad=whole_len={length},atrim=end_sample={length}")
        media.run_ffmpeg(["-i", str(work / (group["source"] + "-ltx.mp4")), "-vn", "-af", af,
                          "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(wav)])
        with wave.open(str(wav), "rb") as handle:
            samples = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2").reshape(-1, 2)
        assert len(samples) == length
        sound.append(samples)
    sound.append(np.zeros((3 * 48000, 2), dtype="<i2"))
    samples = np.concatenate(sound)
    assert len(samples) == 30 * 48000
    foley = edit_folder / "foley.wav"
    with wave.open(str(foley), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(48000)
        handle.writeframes(samples.tobytes())
    normalized = edit_folder / "mix-master.wav"
    measured = media.loudness(foley)
    gain = min(-18 - measured["integrated_lufs"], -1.8 - measured["true_peak_db"])
    media.run_ffmpeg(["-i", str(foley), "-af", f"volume={gain}dB", "-ar", "48000", "-c:a", "pcm_s24le", str(normalized)])
    (edit_folder / "audio-normalization.json").write_text(json.dumps({"input": measured, "gain_db": gain}, indent=2), encoding="utf-8")

    opening = edit_folder / "opening.ass"
    opening.write_text("""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Brand,Manrope,30,&H000C0D0B,&H000C0D0B,&HFF000000,&HFF000000,-1,0,0,0,100,100,1,0,1,0,0,1,76,76,145,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 0,0:00:00.00,0:00:01.50,Brand,,0,0,0,,SiteQuiVend.  /  SELECTED WORK
""", encoding="utf-8")
    escaped_ass = opening.resolve().as_posix().replace(":", "\\:")
    escaped_fonts = (work / "fonts").resolve().as_posix().replace(":", "\\:")
    final = output / "SiteQuiVend-Showreel-30s-Master.mp4"
    media.run_ffmpeg(["-i", str(video), "-i", str(normalized), "-map", "0:v", "-map", "1:a",
                      "-vf", f"setpts=N/(48*TB),ass=filename='{escaped_ass}':fontsdir='{escaped_fonts}'",
                      "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-level:v", "4.2",
                      "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", "-color_primaries", "bt709",
                      "-color_trc", "bt709", "-colorspace", "bt709", "-c:a", "aac", "-b:a", "256k",
                      "-ar", "48000", "-ac", "2", "-t", "30", "-movflags", "+faststart", str(final)])
    web = output / "SiteQuiVend-Showreel-30s-Web.mp4"
    media.run_ffmpeg(["-i", str(final), "-c:v", "libx264", "-preset", "slow", "-crf", "23",
                      "-maxrate", "7M", "-bufsize", "14M", "-profile:v", "high", "-level:v", "4.2",
                      "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", "-c:a", "aac", "-b:a", "160k",
                      "-movflags", "+faststart", str(web)])
    (work / "edit-final.json").write_text(json.dumps(edit, indent=2), encoding="utf-8")
    cover(final, work, output)
    print("EXPORTED", final, web, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--assets-only", action="store_true")
    args = parser.parse_args()
    if args.assets_only:
        assets(args.work)
    else:
        build(args.work.resolve(), args.output.resolve())
