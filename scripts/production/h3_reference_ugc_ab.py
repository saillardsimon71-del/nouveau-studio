#!/usr/bin/env python3
"""Controlled H3 A/B: SAME authentic photo, same French dialogue, same seed and steps.

A: unchanged local Studio UGC shot. B: same shot plus measured licensed-ad
reference/Director voice/acting directions. Both use native H3 audiovisual
generation on ONE Modal GPU worker. This isolates references as the changed
independent variable; quality still requires human review.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

from PIL import Image, ImageOps

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"backend"))
from app.ad_references.library import Library
from app.ad_references.performance import enrich_storyboard, local_storyboard
from app.ad_references.analysis import analyze
from app.ad_references.evaluation import evaluate, compare

OUT=ROOT/"artifacts/h3-voice-AB"
PHOTO_PAGE="https://www.pexels.com/photo/beautiful-woman-in-gray-top-looking-at-camera-4382484/"
PHOTO_URL="https://images.pexels.com/photos/4382484/pexels-photo-4382484.jpeg"
BRIEF="UGC cosmétique française, présentatrice parlant face caméra, 20 secondes"
SEED=20261025
STEPS=20

def make_prompts():
    original=local_storyboard(BRIEF,20,"ugc_presenter")
    ctx=Library().retrieve(BRIEF,"ugc_presenter")
    if not ctx or not any(x["reference_id"]=="licensed_007" for x in ctx["references"]):
        raise RuntimeError("Measured public-domain/CC ad corpus missing: cannot make valid reference B")
    candidate=enrich_storyboard(copy.deepcopy(original),ctx)
    a,b=original.shots[0],candidate.shots[0]
    if a.dialogue!=b.dialogue or a.duration_s!=b.duration_s:
        raise RuntimeError("Not a fair reference-only A/B: script and duration differ")
    if not ctx.get("measured_pace_wpm"):
        raise RuntimeError("Whisper CPU measured rate not present: refuse ungrounded reference B")
    common=(
        "For the target video, at 0.00 seconds, <Picture 1> from [Shot 1] is fully referenced.\n"
        "integrated_multimodal_description: [Shot 1, 0.00s to 5.00s] "
        "Single adult French-speaking female presenter from the EXACT genuine Pexels portrait, "
        "preserving the same face, curly hair, clothing, visible mouth, background and authentic identity. "
        "One continuous photorealistic studio shot: she looks directly toward the viewer and talks. "
        "Correct French mouth shapes synchronized with the speech, accurate hands and human anatomy. "
        "No cut, no text, no logos, no invented bottle, no background speech, no morphing.\n"
    )
    def format_prompt(shot,extra):
        return (
            common + "Director shot direction: "+shot.prompt+"\n"
            "The ONLY spoken words, delivered ON CAMERA by S1, are exactly:\n"
            "(S1) <d>[French] "+shot.dialogue+"</d>\n"
            +extra+"\n"
            "overall_soundscape: One crisp synchronized adult female French voice recorded close to the mouth, "
            "natural faint room tone, no music, no second voice.\n"
            "non_diegetic_music: N/A"
        )
    aa=format_prompt(a,"Neutral professional presenter delivery, natural but no explicit pace or expression coaching.")
    bb=format_prompt(b,
        "Adapt the documented public speaking pace pattern as an upper-bound inspiration, NOT an imitation "
        "of the referenced actor or language: lively, distinctly Parisian conversational French with expressive "
        "natural pitch variation. Start speaking promptly, quick intrigued eyebrow rise on the opening question, "
        "asymmetric smile at the end, one motivated small head tilt. Natural connected syllables, no sustained "
        "vowels, no flat synthesized rhythm. Preserve all existing real-photo identity details."
    )
    return a,b,ctx,aa,bb

def preflight():
    OUT.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(PHOTO_URL,headers={"User-Agent":"Mozilla/5.0 SiteQuiVend-H3-AB"})
    with urllib.request.urlopen(req,timeout=60) as response:
        raw=response.read(25_000_001)
    if not 25000<len(raw)<25000000:
        raise RuntimeError("Real stock photo missing or too large")
    img=ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    if min(img.size)<720:
        raise RuntimeError("Real image too small for reliable I2V")
    ref=ImageOps.fit(img,(768,1344),method=Image.Resampling.LANCZOS,centering=(.5,.46))
    photo=OUT/"real_pexels_firstframe.png"
    ref.save(photo,optimize=True)
    shot_a,shot_b,context,prompt_a,prompt_b=make_prompts()
    obj={
        "brief":BRIEF,"source_photo":PHOTO_PAGE,
        "source_image_sha256":hashlib.sha256(raw).hexdigest(),
        "first_frame_sha256":hashlib.sha256(photo.read_bytes()).hexdigest(),
        "dialogue":shot_a.dialogue,"duration_each_s":shot_a.duration_s,
        "seed_identical":SEED,"steps_identical":STEPS,
        "reference_ids":[x["reference_id"] for x in context["references"]],
        "measured_wpm_from_reference":context.get("measured_pace_wpm"),
        "not_french_training_rate":"The measured cited ad is English-language; French target remains editorially adapted.",
        "A_no_reference":{"director_prompt":shot_a.prompt,"h3_prompt":prompt_a},
        "B_with_reference":{"director_prompt":shot_b.prompt,"h3_prompt":prompt_b,
                            "provenance":shot_b.creative_provenance},
        "videos_generated":False
    }
    (OUT/"AB_PROMPTS.json").write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
    print("CHECK PASS: same image/dialogue/5s/20steps/seed, A and B differ only in Director reference guidance",flush=True)

def render():
    import modal
    conf=json.loads((OUT/"AB_PROMPTS.json").read_text(encoding="utf-8"))
    encoded=base64.b64encode((OUT/"real_pexels_firstframe.png").read_bytes()).decode("ascii")
    common={"duration_s":conf["duration_each_s"],"aspect_ratio":"9:16",
            "seed":SEED,"steps":STEPS,"audio_mode":"native","image_png_base64":encoded}
    reqs=[{**common,"prompt":conf["A_no_reference"]["h3_prompt"]},
          {**common,"prompt":conf["B_with_reference"]["h3_prompt"]}]
    fn=modal.Function.from_name("pvs-minimax-h3","render_batch",environment_name="main").hydrate()
    print("Rendering exactly TWO 20-step H3 clips in one Modal batch; no retries",flush=True)
    result=fn.remote(reqs)
    if len(result.get("shots",[]))!=2:
        raise RuntimeError("H3 did not complete both clips")
    info=[]
    for code,clip in zip(("A","B"),result["shots"]):
        blob=base64.b64decode(clip["video_base64"],validate=True)
        if not 30000<len(blob)<25000000:raise RuntimeError("Invalid H3 video")
        path=OUT/("H3-"+code+".mp4");path.write_bytes(blob)
        info.append({"version":code,"file":str(path),"bytes":len(blob),
                     "sha256":hashlib.sha256(blob).hexdigest(),"metadata":clip.get("metadata",{})})
        print("RENDERED H3-"+code+" "+str(len(blob))+" bytes",flush=True)
    conf["videos_generated"]=True
    conf["output_files"]=info
    conf["gpu_batch_wall_sec"]=result.get("batch_wall_seconds")
    (OUT/"AB_PROMPTS.json").write_text(json.dumps(conf,ensure_ascii=False,indent=2),encoding="utf-8")

def evaluate_outputs():
    conf=json.loads((OUT/"AB_PROMPTS.json").read_text(encoding="utf-8"))
    results={}
    whisper_checkpoint=OUT/"whisper-tiny.pt"
    # Download CPU Whisper checkpoint only AFTER both actual videos are secured.
    # Errors in ASR must not erase successful video artifacts.
    try:
        import whisper
        cache=OUT/"models"
        cache.mkdir(exist_ok=True)
        whisper.load_model("tiny",download_root=str(cache),device="cpu")
        model=cache/"tiny.pt"
    except Exception as exc:
        model=None
        print("ASR setup unavailable, video artifacts retained: "+str(exc),flush=True)
    for code in ("A","B"):
        p=OUT/("H3-"+code+".mp4")
        if not p.is_file():raise RuntimeError("Missing completed H3 clip "+code)
        meta=subprocess.check_output(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(p)],text=True)
        j=json.loads(meta)
        if not any(s.get("codec_type")=="video" for s in j["streams"]) or not any(s.get("codec_type")=="audio" for s in j["streams"]):
            raise RuntimeError("Missing native audiovisual track in "+code)
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(p),
                        "-vn","-ar","16000","-ac","1",str(OUT/("audio-"+code+".wav"))],check=True)
        for time_s in (0.5,2.5,4.5):
            subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss",str(time_s),"-i",str(p),
                            "-frames:v","1",str(OUT/f"{code}-{time_s:.1f}s.jpg")],check=True)
        results[code]={"video_duration":float(j["format"]["duration"]),"audio_track":True}
        try:
            analysis=analyze(p,OUT/("analysis-"+code),
                authorization="Agency-owned MiniMax H3 generated video from Pexels licensed reference",
                whisper_model=model if model and model.is_file() else None,language="fr")
            ev=evaluate(analysis,conf["dialogue"],"ugc_fr_same_brief",code)
            results[code]["evaluation"]=ev
        except Exception as exc:
            results[code]["analysis_error"]=type(exc).__name__+": "+str(exc)[:280]
    if "evaluation" in results["A"] and "evaluation" in results["B"]:
        try:
            results["comparison"]=compare(results["A"]["evaluation"],results["B"]["evaluation"])
        except Exception as exc:
            results["comparison_error"]=str(exc)
    results["quality_statement"]="No objective winner claimed. Manual listening and lip/facial review are mandatory."
    (OUT/"AB_EVALUATION.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print("A/B technical analysis complete (manual QC still required)",flush=True)

if __name__=="__main__":
    from argparse import ArgumentParser
    p=ArgumentParser()
    p.add_argument("stage",choices=["preflight","render","evaluate"])
    stage=p.parse_args().stage
    {"preflight":preflight,"render":render,"evaluate":evaluate_outputs}[stage]()
