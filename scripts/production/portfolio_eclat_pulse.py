#!/usr/bin/env python3
import argparse
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import random
import subprocess
import time
import urllib.request
import wave
from array import array

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path("artifacts/portfolio-20261026")
SIZE = (768, 1344)
FPS = 24
FILMS = {
    "eclat-02": {
        "title": "ÉCLAT / 02", "subtitle": "LA LUMIÈRE, À FLEUR DE PEAU",
        "music": "reverie", "music_date": "2020/03", "music_start": 45,
        "trim": 4.75, "card": 1.75, "duration": 15.5,
        "shots": [
            {"name": "essence", "id": 6693978, "author": "Tara Winstead",
             "page": "https://www.pexels.com/photo/bottle-with-dropper-6693978/",
             "crop": [.28, .28, .75, .85], "seed": 26102601,
             "prompt": "Prestige skincare commercial. Extreme macro of the authentic glass pipette and amber glass from this real photograph. The crop deliberately excludes the cap. A tiny glistening meniscus of clear serum moves slowly inside the transparent pipette; one small droplet catches a soft warm reflection. Controlled 2 cm lateral macro camera slide, exquisite specular highlights, shallow optical depth of field, warm ivory background, natural transparent liquid physics. Keep the exact glass geometry and original composition. One uninterrupted cinematic take, restrained and sensual. No new hands, no new bottle, no text, no labels, no logos. Silent human subjects; audio contains only a tiny liquid tick and soft room tone. No speech, no whisper, no vocals, no music."},
            {"name": "caresse", "id": 6417954, "author": "Pavel Danilyuk",
             "page": "https://www.pexels.com/photo/person-woman-hand-face-6417954/",
             "crop": [0, .03, 1, 1], "seed": 26102602,
             "prompt": "Luxury skincare beauty film from the authentic photograph. Preserve the exact adult woman's face, skin texture, fingers, transparent pipette and white clothing. A single tiny drop of serum touches her cheek beneath the eye, then her hand withdraws only two centimeters; her expression stays calm and relaxed, lips closed. An exceptionally slow cinematic camera push of a few centimeters. Soft diffused ivory window light, luminous natural skin, warm neutral color, shallow depth of field, elegant restrained beauty photography. No speaking or moving lips. No additional fingers, no warped pipette, no new product packaging, no text, no letters, no logo, no cut. Audio: extremely soft liquid touch and cloth rustle only, no voice, no whisper, no song or music."},
            {"name": "packshot", "id": 8101511, "author": "Polina",
             "page": "https://www.pexels.com/photo/close-up-photo-of-serum-bottles-8101511/",
             "crop": [.59, .30, 1, 1], "seed": 26102603,
             "prompt": "Impeccable luxury skincare product packshot, the exact single amber glass serum bottle with white dropper cap and COMPLETELY BLANK white paper label from this authentic photograph. Bottle stays upright, sealed, rigid and absolutely stationary on the same ivory textured linen. A slow, very short lateral dolly produces delicate parallax and a soft golden highlight travels along the curved amber shoulder. Keep precisely the same blank label, white cap, bottle silhouette, cloth and light direction. Warm cream and champagne palette, refined optical detail, soft window light and long elegant shadows. Only this one bottle, no additions, no opening cap, no hands, no new props. No letters or generated text anywhere. Audio: near-silent airy room tone, no voice, no whisper, no music."},
        ],
    },
    "pulse-01": {
        "title": "PULSE / 01", "subtitle": "CHAQUE MOUVEMENT COMPTE",
        "music": "catalyst", "music_date": "2020/06", "music_start": 52,
        "trim": 4.0, "card": 1.25, "duration": 13.25,
        "shots": [
            {"name": "focus", "id": 4754140, "author": "cottonbro studio",
             "page": "https://www.pexels.com/photo/woman-in-black-sports-bra-and-black-shorts-4754140/",
             "crop": [0, 0, 1, 1], "seed": 26102611,
             "prompt": "Premium activewear campaign. Keep the exact athletic adult female boxer, braided hair, graphite sports bra, black gloves and industrial boxing gym from this real photograph. She lifts her gaze with fierce focus and raises her gloved hands just slightly into a compact guard; a controlled athletic breath moves the ribbed performance fabric. Cinematic short lateral tracking camera, steel blue shadows, bright white rim light through the windows, dramatic contrast, fine realistic sweat and tactile technical fabric. Preserve identity, body anatomy and original garment seams. Short purposeful movement, no punch, no new people or equipment, no extra fingers or arms, no logos or text. Sound: close fabric rustle and glove leather creak, no vocal breath, no words, no dialogue, no singing and no music."},
            {"name": "drive", "id": 4753990, "author": "cottonbro studio",
             "page": "https://www.pexels.com/photo/woman-in-white-tank-top-and-black-shorts-sitting-on-brown-wooden-floor-4753990/",
             "crop": [0, .05, 1, 1], "seed": 26102612,
             "prompt": "A cinematic premium activewear campaign, same exact adult female athlete with two braids and graphite ribbed sports bra in this authentic industrial boxing gym photograph. Starting in the photographed low push-up position gripping the two stationary hexagonal dumbbells, she presses smoothly upward ONCE by a short distance with plausible shoulder and elbow mechanics, then holds. Her hands remain planted on the exact dumbbell handles, weights never slide. Camera is low and makes a small energetic forward tracking move, strong cool window rim light, rich dark shadows, crisp fabric texture and natural sweat. Preserve her face, outfit, braids, gym and body proportions. No extra limbs, no fast repetitions, no camera spin, no added objects, no brand or lettering. Audio: weight contact, subtle floor impact, fabric stretch only; no human voice, no words, no grunts, no singing, no music."},
            {"name": "resolve", "id": 4753988, "author": "cottonbro studio",
             "page": "https://www.pexels.com/photo/woman-in-black-sports-bra-and-black-shorts-doing-exercise-4753988/",
             "crop": [0, 0, 1, 1], "seed": 26102613,
             "prompt": "Cinematic sportswear campaign finale from the authentic photo. Preserve this exact adult female athlete, two tight braids, graphite sports bra and shorts, black boxing gloves and same industrial gym. Seated at the edge of the ring, she slowly lifts her head and locks a determined forward gaze, gently lowering the glove from her forehead toward her chin in one small controlled movement. Subtle real fabric movement and sweat highlights, powerful composed silhouette. A short low lateral dolly reveals window light, cool charcoal shadows, tactile ribbed activewear, silver-blue rim, premium cinematic contrast. Keep exact body, face, hands, gloves and original gym. No new limbs or people, no smile, no text, no visible brand, no speech. Audio: glove leather, restrained sports fabric and room tone; no voice, no singing, no words and no music."},
        ],
    },
}


def command(args):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-5000:])
    return p.stdout


def probe(path):
    return json.loads(command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))


def download(url, target):
    if not target.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SiteQuiVend-Portfolio"})
        with urllib.request.urlopen(req, timeout=120) as response:
            data = response.read(30_000_001)
        if not 20_000 < len(data) <= 30_000_000:
            raise ValueError("Unexpected source size: " + url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def prepare():
    records = []
    contact = Image.new("RGB", (768 * 3, 1344 * 2), "#222222")
    for row, (key, film) in enumerate(FILMS.items()):
        folder = ROOT / key
        for col, shot in enumerate(film["shots"]):
            url = f"https://images.pexels.com/photos/{shot['id']}/pexels-photo-{shot['id']}.jpeg"
            original = folder / "references" / f"{shot['name']}-original.jpg"
            download(url, original)
            im = ImageOps.exif_transpose(Image.open(original)).convert("RGB")
            w, h = im.size
            box = tuple(round(x * dim) for x, dim in zip(shot["crop"], [w, h, w, h]))
            cropped = im.crop(box)
            if min(cropped.size) < 768:
                raise ValueError(f"Source crop resolution too low: {key}/{shot['name']} {cropped.size}")
            frame = ImageOps.fit(cropped, SIZE, method=Image.Resampling.LANCZOS)
            first = original.with_name(shot["name"] + "-firstframe.png")
            frame.save(first, optimize=True)
            contact.paste(frame, (col * 768, row * 1344))
            records.append({"film": key, **shot, "download": url,
                            "original_dimensions": im.size, "crop_pixels": box,
                            "source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                            "firstframe_sha256": hashlib.sha256(first.read_bytes()).hexdigest()})
        music_url = f"https://www.scottbuckley.com.au/library/wp-content/uploads/{film['music_date']}/sb_{film['music']}.mp3"
        music = folder / "music" / (film["music"] + ".mp3")
        download(music_url, music)
        audio = probe(music)
        assert any(s["codec_type"] == "audio" for s in audio["streams"])
        assert float(audio["format"]["duration"]) > film["music_start"] + film["duration"]
    contact.thumbnail((1152, 1344))
    contact.save(ROOT / "storyboard-real-sources.jpg", quality=94)
    (ROOT / "sources.json").write_text(json.dumps({
        "reference": "MAISON 01 - Actions 40188342628; 20 steps; res_multistep/simple; L40S; native 768x1344/24fps",
        "photos": records, "photo_license": "https://www.pexels.com/license/",
        "music": [{"film": key, "title": film["music"].title(), "author": "Scott Buckley",
                   "page": f"https://www.scottbuckley.com.au/library/{film['music']}/",
                   "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/"}
                  for key, film in FILMS.items()],
        "rights_review": "Not certified; user explicitly excluded licensing review on 2026-10-26.",
        "sources": "Authentic photographs only; crop and resize, no AI still generation.",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("CPU PREFLIGHT PASS: six photo crops, source hashes, two soundtracks, no GPU", flush=True)


def render(key):
    import modal
    film = FILMS[key]
    folder = ROOT / key
    payloads = []
    for shot in film["shots"]:
        frame = folder / "references" / (shot["name"] + "-firstframe.png")
        payloads.append({"prompt": shot["prompt"], "duration_s": 5 if key == "eclat-02" else 4,
                         "aspect_ratio": "9:16", "seed": shot["seed"], "steps": 20,
                         "audio_mode": "native", "image_png_base64": base64.b64encode(frame.read_bytes()).decode()})
    target = folder / "clips"
    target.mkdir(exist_ok=True)
    if any(target.glob("*.mp4")):
        raise RuntimeError("Existing paid clips found; refusing an automatic regeneration")
    func = modal.Function.from_name("pvs-minimax-h3", "render_batch", environment_name="main").hydrate()
    print(f"Starting {key}: ONE batch, THREE shots, 20 steps, existing deployed worker, no retry", flush=True)
    result = func.remote(payloads)
    assert len(result["shots"]) == 3
    report = []
    for shot, item in zip(film["shots"], result["shots"]):
        path = target / (shot["name"] + "-h3.mp4")
        raw = base64.b64decode(item["video_base64"], validate=True)
        path.write_bytes(raw)
        info = probe(path)
        assert any(s["codec_type"] == "video" and s["width"] == 768 and s["height"] == 1344 for s in info["streams"])
        assert float(info["format"]["duration"]) >= film["trim"]
        report.append({"shot": shot["name"], **item["metadata"], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        print("SAVED " + str(path), flush=True)
    (folder / "render-report.json").write_text(json.dumps({"batch_wall_seconds": result["batch_wall_seconds"], "shots": report}, indent=2))


def font_path(serif=False):
    paths = (["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "C:/Windows/Fonts/georgia.ttf"] if serif else
             ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"])
    return next(p for p in paths if Path(p).is_file())


def endcard(key, path):
    film = FILMS[key]
    beauty = key == "eclat-02"
    im = Image.new("RGB", (1080, 1920), "#eee8dd" if beauty else "#0a1016")
    d = ImageDraw.Draw(im)
    ink = "#473b30" if beauty else "#eef4f7"
    accent = "#9a7b52" if beauty else "#c5ee3a"
    d.text((540, 820), film["title"], font=ImageFont.truetype(font_path(beauty), 108), anchor="mm", fill=ink)
    d.line((370, 925, 710, 925), fill=accent, width=2 if beauty else 5)
    d.text((540, 1000), film["subtitle"], font=ImageFont.truetype(font_path(), 28), anchor="mm", fill=ink)
    d.text((540, 1740), "CONCEPT FILM  /  SITEQUIVEND", font=ImageFont.truetype(font_path(), 23), anchor="mm", fill=accent)
    im.save(path)


def sound_design(key, path):
    rate = 48000
    samples = [0.0] * round(FILMS[key]["duration"] * rate)
    rng = random.Random(261026)
    events = ([(.18, "glass", .10), (1.1, "glass", .055), (4.5, "air", .055),
               (9.0, "glass", .065), (13.5, "air", .07)] if key == "eclat-02" else
              [(0, "impact", .30), (1.5, "impact", .12), (3.8, "air", .16),
               (4.0, "impact", .34), (6.0, "impact", .19), (7.8, "air", .14),
               (8.0, "impact", .29), (11.8, "air", .18), (12.0, "impact", .32)])
    for start, kind, gain in events:
        duration = .48 if kind == "air" else .30
        low = 0.0
        for i in range(round(duration * rate)):
            t = i / rate
            j = round(start * rate) + i
            if j >= len(samples):
                break
            noise = rng.uniform(-1, 1)
            low = .82 * low + .18 * noise
            if kind == "glass":
                value = (math.sin(2 * math.pi * (1450 * t - 900 * t * t)) + .3 * math.sin(2 * math.pi * 2850 * t)) * math.exp(-t * 29) * min(t * 1000, 1)
            elif kind == "impact":
                value = (.8 * math.sin(2 * math.pi * (92 * t - 65 * t * t)) + .5 * low) * math.exp(-t * 19) * min(t * 1800, 1)
            else:
                value = (noise - low) * math.sin(math.pi * t / duration) ** 3 * .55
            samples[j] += gain * value
    pcm = array("h")
    for value in samples:
        level = round(max(-.99, min(.99, value)) * 32767)
        pcm.extend([level, level])
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())


def assemble(key):
    film = FILMS[key]
    folder = ROOT / key
    prepared = folder / "prepared"
    exports = folder / "exports"
    prepared.mkdir(exist_ok=True)
    exports.mkdir(exist_ok=True)
    for shot in film["shots"]:
        src = folder / "clips" / (shot["name"] + "-h3.mp4")
        info = probe(src)
        assert float(info["format"]["duration"]) >= film["trim"]
        grade = "eq=contrast=1.025:saturation=0.93:brightness=0.006,colorbalance=rs=0.012:bs=-0.012" if key == "eclat-02" else "eq=contrast=1.07:saturation=0.76,colorbalance=bs=0.025:rs=-0.012"
        command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-t", str(film["trim"]),
                 "-vf", "fps=24,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1," + grade + ",format=yuv420p",
                 "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "17", str(prepared / (shot["name"] + ".mp4"))])
    card = prepared / "endcard.png"
    endcard(key, card)
    command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", str(card), "-t", str(film["card"]),
             "-r", "24", "-vf", "format=yuv420p,setsar=1", "-an", "-c:v", "libx264", "-crf", "17", str(prepared / "endcard.mp4")])
    paths = [prepared / (s["name"] + ".mp4") for s in film["shots"]]
    if key == "eclat-02":
        command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(paths[0]), "-i", str(paths[1]), "-i", str(paths[2]),
                 "-filter_complex", "[0:v][1:v]xfade=transition=fade:duration=0.25:offset=4.5[x];[x][2:v]xfade=transition=fade:duration=0.25:offset=9[v]",
                 "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "17", str(prepared / "shots.mp4")])
        paths = [prepared / "shots.mp4"]
    paths.append(prepared / "endcard.mp4")
    listing = prepared / "concat.txt"
    listing.write_text("".join("file '" + p.resolve().as_posix() + "'\n" for p in paths), encoding="utf-8")
    command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(prepared / "picture.mp4")])
    seconds = film["duration"]
    effects = prepared / "original-sound-design.wav"
    sound_design(key, effects)
    final = exports / (key.upper() + "-MASTER-1080x1920.mp4")
    command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(prepared / "picture.mp4"),
             "-ss", str(film["music_start"]), "-i", str(folder / "music" / (film["music"] + ".mp3")),
             "-i", str(effects),
             "-filter_complex", f"[1:a]atrim=0:{seconds},asetpts=PTS-STARTPTS,afade=t=in:d=0.12,afade=t=out:st={seconds-0.65}:d=0.65,volume=0.82[m];[m][2:a]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=9[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t", str(seconds), "-movflags", "+faststart", str(final)])
    web = exports / (key.upper() + "-WEB-720x1280.mp4")
    command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(final), "-vf", "scale=720:1280:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(web)])
    for p in [final, web]:
        info = probe(p)
        assert abs(float(info["format"]["duration"]) - seconds) < .15
        assert {s["codec_type"] for s in info["streams"]} >= {"audio", "video"}
        command(["ffmpeg", "-v", "error", "-i", str(p), "-f", "null", "-"])
    command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "1", "-i", str(final), "-frames:v", "1", str(exports / (key.upper() + "-COVER.jpg"))])
    command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(final), "-vf", "fps=2,scale=180:320,tile=8x4", "-frames:v", "1", str(exports / (key.upper() + "-CONTACT.jpg"))])
    (exports / "CREDITS.txt").write_text("Independent fictional concept film. AI-animated real photographs.\n" +
        "\n".join(s["author"] + " - " + s["page"] for s in film["shots"]) +
        "\nPexels: https://www.pexels.com/license/\nMusic: '" + film["music"].title() +
        "' by Scott Buckley - CC BY 4.0 - www.scottbuckley.com.au\n" +
        "https://www.scottbuckley.com.au/library/" + film["music"] + "/\nMusic edited, trimmed and normalized. Include this music credit wherever published.\nOriginal synthetic sound design: SiteQuiVend, 2026. No voice recordings used.\n", encoding="utf-8")
    (exports / "delivery.json").write_text(json.dumps({"film": key, "duration": seconds,
        "source": "768x1344 H3, cropped and upscaled to 1080x1920", "fps": 24,
        "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in [final, web]],
        "qc": "Technical decode passed; visual and listening inspection still required.",
        "audio": "Instrumental score and original glass, air and impact sound design. Native H3 audio excluded; no voice recording used."}, indent=2))
    print("EXPORTED " + str(final), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["prepare", "render", "assemble"])
    p.add_argument("--film", choices=list(FILMS))
    args = p.parse_args()
    if args.phase == "prepare":
        prepare()
    elif args.phase == "render":
        render(args.film)
    else:
        assemble(args.film)
