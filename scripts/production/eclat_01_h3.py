#!/usr/bin/env python3
"""ÉCLAT / 01: fully edited French beauty concept commercial from real Pexels photos.

One existing real H3 French speaking portrait is reused from run 40192700348.
Two new H3 clips use the already deployed Modal render_batch function (20 steps).
All STILL images are real stock photographs; no AI-generated first frames.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import urllib.request

from PIL import Image, ImageOps

ROOT = Path("artifacts/eclat01")
REFS = ROOT / "references"
CLIPS = ROOT / "clips"
OUT = ROOT / "exports"
SIZE = (768, 1344)
HERO_TRIM = 4.40
NEW_TRIM = 4.65
CARD_SECONDS = 2.30
MASTER = "ECLAT-01-SITEQUIVEND-FRENCH-AD-H3.mp4"
SOURCE = {
    "id": 5069440,
    "photographer": "Anna Shvets",
    "page": "https://www.pexels.com/photo/crop-attractive-woman-with-towel-on-head-demonstrating-cosmetic-product-5069440/",
    "image": "https://images.pexels.com/photos/5069440/pexels-photo-5069440.jpeg",
    "license": "https://www.pexels.com/license/",
}
SCORE_URL = "https://www.scottbuckley.com.au/library/wp-content/uploads/2019/02/sb_ascension.mp3"
SCORE_PAGE = "https://www.scottbuckley.com.au/library/ascension/"
SHOTS = [
    {
        "name": "beauty-spokesperson",
        "center": (0.50, 0.44),
        "seed": 202610251,
        "prompt": """For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1, 0.00s to 5.00s] A believable premium French cosmetic commercial from the EXACT genuine high-resolution photography in <Picture 1>. The adult woman with hair wrapped in a towel holds her exact real photographed skincare bottle. Preserve her true face, uncovered lips, hands, bottle, wardrobe, background, reflections and naturally textured skin. She makes direct, reassuring eye contact with the lens, slowly lifts the bottle by two centimeters, and speaks directly TO CAMERA with precise lip-synchronization. (S1) says in metropolitan French: <d>[French] Et si le luxe commençait par prendre soin de soi ?</d> VOICE DIRECTION: elegant warm female voice, immediately inviting, slight curious lift on 'Et si', subtle smile on 'luxe', slow reassuring cadence on 'prendre soin de soi', crisp French vowels, no shouting, no robotic rhythm. A single relaxed hand movement, one natural blink, shallow depth of field, luxury beauty-film lighting, anatomically exact fingers, no changes to label or bottle geometry. No artificial packaging, no text, no subtitles, no scene cuts.

overall_soundscape: Only S1 speaks on-screen, in clean synchronized studio-like French speech; restrained beauty room ambience; no second voice, no English words.

non_diegetic_music: N/A"""
    },
    {
        "name": "ritual-detail",
        "center": (0.56, 0.48),
        "seed": 202610252,
        "prompt": """For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1, 0.00s to 5.00s] The real photographed skincare bottle and the hand holding it from <Picture 1> are the hero of an extremely high-end editorial beauty-film closeup. KEEP the EXACT SAME real product, cap, original packaging and original photographed appearance. A luxurious 8-centimeter cinematic macro camera move reveals delicately shifting highlights on the bottle, a minor soft wrist movement, the towel and skin becoming beautiful background bokeh. Maintain the existing bottle structure, preserve every finger, no arbitrary color or object change. No animated captions or new branding. Audio: a soft intimate cosmetic-commercial ambiance with a delicate glass handling sound. No spoken words; no disembodied voices. Warm ivory and champagne tones with controlled depth, natural photographic detail and sophistication throughout.

overall_soundscape: Subtle tactile room tone and soft glass contact only, no speech, no music.

non_diegetic_music: N/A"""
    }
]

def cmd(args: list[str]) -> str:
    p = subprocess.run(args, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError("Command failed: " + " ".join(args[:4]) + "\n" + p.stderr[-2500:])
    return p.stdout.strip()

def fetch(url: str, limit: int=25000000) -> bytes:
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 SiteQuiVend-Eclat/1.0"})
    with urllib.request.urlopen(req, timeout=80) as r:
        raw=r.read(limit+1)
    if not 25000 < len(raw) <= limit:
        raise ValueError("Unexpected real-photo/music asset length")
    return raw

def preflight():
    REFS.mkdir(parents=True,exist_ok=True)
    original=REFS/"real-pexels-original.jpg"
    original.write_bytes(fetch(SOURCE["image"]))
    data=original.read_bytes()
    img=ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    if min(img.size)<720:
        raise RuntimeError(f"Pexels photo too low resolution: {img.size}")
    refs=[]
    for item in SHOTS:
        prepared=ImageOps.fit(img,SIZE,centering=item["center"],method=Image.Resampling.LANCZOS)
        target=REFS/(item["name"]+".png")
        prepared.save(target,optimize=True)
        if target.stat().st_size > 24*1024*1024:
            raise RuntimeError("Pexels PNG exceeds Modal H3 image limit")
        refs.append({"shot":item["name"],"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"resolution":list(SIZE)})
    music=ROOT/"score.mp3"
    music.write_bytes(fetch(SCORE_URL))
    score_probe=json.loads(cmd(["ffprobe","-v","error","-show_streams","-of","json",str(music)]))
    if not any(x.get("codec_type")=="audio" for x in score_probe.get("streams",[])):
        raise RuntimeError("Licensed music missing audio")
    provenance={
        "fictional_brand":"ECLAT / 01",
        "description":"Noncommissioned fictional skincare concept; not an actual brand endorsement",
        "real_first_frame_photography":{**SOURCE,"original_dimensions":list(img.size),"sha256":hashlib.sha256(data).hexdigest()},
        "frames":refs,
        "first_plan_reused":"GitHub Actions run 40192700348, H3 native French voice test (already generated)",
        "soundtrack":{"name":"Ascension","artist":"Scott Buckley","license":"CC BY 4.0","page":SCORE_PAGE},
        "important":"No extra AI still imagery; no new logos or unsupported product claims"
    }
    (ROOT/"provenance.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PREFLIGHT OK: authentic Pexels photograph, 2 firstframes, real licensed music; zero GPU",flush=True)

def render():
    import modal
    requests=[]
    for item in SHOTS:
        photo=REFS/(item["name"]+".png")
        if not photo.is_file():
            raise RuntimeError("Authentic photo missing: "+str(photo))
        requests.append({
            "prompt":item["prompt"],"duration_s":5.0,"aspect_ratio":"9:16","seed":item["seed"],
            "steps":20,"audio_mode":"native",
            "image_png_base64":base64.b64encode(photo.read_bytes()).decode("ascii")
        })
    fn=modal.Function.from_name("pvs-minimax-h3","render_batch",environment_name="main").hydrate()
    print("RUNNING TWO 20-step real-photo H3 scenes in one Modal GPU job, no API and no retries",flush=True)
    result=fn.remote(requests)
    returned=result.get("shots",[])
    if len(returned)!=2:
        raise RuntimeError("Incomplete Modal H3 batch; do not assemble or silently retry")
    CLIPS.mkdir(parents=True,exist_ok=True)
    reports=[]
    for item,shot in zip(SHOTS,returned):
        raw=base64.b64decode(shot["video_base64"],validate=True)
        if not 30000<len(raw)<25000000:
            raise RuntimeError("Invalid or too-large MP4: "+item["name"])
        dst=CLIPS/(item["name"]+".mp4")
        dst.write_bytes(raw)
        reports.append({"name":item["name"],"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),**shot.get("metadata",{})})
        print("SAVED REAL "+str(dst)+" "+str(len(raw))+" bytes",flush=True)
    (ROOT/"render-report.json").write_text(json.dumps({"batch_wall_seconds":result.get("batch_wall_seconds"),"scenes":reports},indent=2),encoding="utf-8")

def prepare_one(src:Path,dst:Path,seconds:float):
    if not src.is_file() or src.stat().st_size<30000:
        raise FileNotFoundError(str(src))
    meta=json.loads(cmd(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(src)]))
    if float(meta.get("format",{}).get("duration",0))<seconds:
        raise RuntimeError("H3 scene too short: "+str(src))
    if not any(s.get("codec_type")=="audio" for s in meta.get("streams",[])):
        raise RuntimeError("Missing native H3 sound: "+str(src))
    cmd(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(src),"-t",str(seconds),
         "-vf","fps=24,scale=1080:1920:flags=lanczos,setsar=1,format=yuv420p",
         "-r","24","-c:v","libx264","-preset","medium","-crf","18",
         "-c:a","aac","-ar","48000","-ac","2","-b:a","192k","-af","aresample=async=1:first_pts=0",
         "-movflags","+faststart",str(dst)])

def assemble():
    hero=ROOT/"hero"/"H3-AVATAR-VOIX-FR-TEST.mp4"
    if not hero.is_file(): raise FileNotFoundError("Approved prior French H3 clip not recovered")
    prepared=ROOT/"prepared"
    prepared.mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
    segments=[("hero",hero,HERO_TRIM)]+[(s["name"],CLIPS/(s["name"]+".mp4"),NEW_TRIM) for s in SHOTS]
    ready=[]
    for name,src,trim in segments:
        dst=prepared/(name+".mp4")
        prepare_one(src,dst,trim)
        ready.append(dst)
    card=prepared/"endcard.mp4"
    vf=(
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf:"
        "text='ECLAT / 01':fontcolor=0xF5EEE1:fontsize=84:x=(w-text_w)/2:y=807,"
        "drawbox=x=318:y=925:w=444:h=2:color=0xC9AD88@0.8:t=fill,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "text='LE RITUEL DE SOI':fontcolor=0xC9AD88:fontsize=29:x=(w-text_w)/2:y=1003,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "text='CONCEPT - SITEQUIVEND.FR':fontcolor=0xC0C0C0:fontsize=23:x=(w-text_w)/2:y=1150,"
        "format=yuv420p"
    )
    cmd(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","lavfi","-i",
         f"color=c=0x13120F:s=1080x1920:r=24:d={CARD_SECONDS}",
         "-f","lavfi","-i","anullsrc=channel_layout=stereo:sample_rate=48000",
         "-vf",vf,"-t",str(CARD_SECONDS),"-c:v","libx264","-crf","18","-preset","fast",
         "-c:a","aac","-b:a","192k","-shortest",str(card)])
    ready.append(card)
    listing=prepared/"concat.txt"
    listing.write_text("".join("file '"+str(p.resolve())+"'\n" for p in ready),encoding="utf-8")
    base=prepared/"picture_audio.mp4"
    cmd(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",str(listing),
         "-c:v","libx264","-preset","medium","-crf","18","-c:a","aac","-b:a","192k",str(base)])
    score=ROOT/"score.mp3"
    if not score.is_file(): raise FileNotFoundError("Music not downloaded")
    final=OUT/MASTER
    length=HERO_TRIM+2*NEW_TRIM+CARD_SECONDS
    # Low-volume licensed score under the native French dialogue.
    cmd(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(base),"-ss","42","-i",str(score),
         "-filter_complex",
         f"[1:a]atrim=0:{length},asetpts=PTS-STARTPTS,volume=0.075,"
         f"afade=t=in:st=0:d=0.3,afade=t=out:st={length-1.2}:d=1.2[m];"
         "[0:a][m]amix=inputs=2:duration=first:normalize=0,"
         "alimiter=limit=0.95[a]",
         "-map","0:v","-map","[a]","-c:v","copy","-c:a","aac","-b:a","192k",
         "-t",str(length),"-movflags","+faststart",str(final)])
    info=json.loads(cmd(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(final)]))
    streams=info.get("streams",[])
    vids=[s for s in streams if s.get("codec_type")=="video"]
    auds=[s for s in streams if s.get("codec_type")=="audio"]
    if len(vids)!=1 or len(auds)!=1:
        raise RuntimeError("Final ad must have exactly one video and one audio stream")
    if (int(vids[0].get("width",0)),int(vids[0].get("height",0)))!=(1080,1920):
        raise RuntimeError("Unexpected final resolution")
    actual=float(info["format"]["duration"])
    if not abs(actual-length)<0.4:
        raise RuntimeError(f"Duration mismatch {actual:.2f} vs {length:.2f}")
    thumb=OUT/"ECLAT-01-cover.jpg"
    cmd(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss","2","-i",str(final),"-frames:v","1",str(thumb)])
    web=OUT/"ECLAT-01-site-720p.mp4"
    cmd(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(final),
         "-vf","scale=720:1280:flags=lanczos",
         "-c:v","libx264","-preset","fast","-crf","24","-c:a","aac","-b:a","128k",
         "-movflags","+faststart",str(web)])
    (OUT/"CREDITS.txt").write_text(
        "ÉCLAT / 01 — fictional, uncommissioned commercial concept; not a real skincare brand.\n"
        "The filmed people and photographed cosmetics do not endorse this concept.\n"
        "Photo: Anastasiya Gepp — https://www.pexels.com/photo/beautiful-woman-in-gray-top-looking-at-camera-4382484/\n"
        f"Photo: {SOURCE['photographer']} — {SOURCE['page']}\n"
        "Stock photograph license: https://www.pexels.com/license/\n"
        "Music: 'Ascension' by Scott Buckley, CC BY 4.0, www.scottbuckley.com.au\n",
        encoding="utf-8")
    (OUT/"delivery.json").write_text(json.dumps({
        "brand":"ÉCLAT / 01","fictional_concept":True,
        "master":MASTER,"web":web.name,"duration_sec":actual,"width":1080,"height":1920,
        "audio":"French native MiniMax H3 speech + licensed score",
        "status":"TECHNICALLY_EXPORTED_NEEDS_HUMAN_QC",
        "inspect":["spoken French wording","intonation","lip sync","hands and bottle stability","music mix","visible brand marks"],
        "master_sha256":hashlib.sha256(final.read_bytes()).hexdigest()
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"FINAL EXPORTED {final} ({actual:.2f}s); HUMAN QC REQUIRED",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=["preflight","render","assemble"])
    {"preflight":preflight,"render":render,"assemble":assemble}[parser.parse_args().stage]()
