import base64
import io
import json
import time
from pathlib import Path

import modal

app = modal.App("pvs-sitequivend-audio")
cache = modal.Volume.from_name("pvs-commercial-audio-models", create_if_missing=True)
REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"
PARAGRAPHS = [
    "Votre activité mérite mieux qu'une vidéo ordinaire. Un produit, une table, un lieu.",
    "Et soudain, une autre dimension. Votre idée, vos photos, vos vidéos : nous les transformons en publicités qui captent l'attention.",
    "Création, voix, montage. Une seule signature. Site qui vend. Parlons de votre projet.",
]

image = (modal.Image.debian_slim(python_version="3.11")
         .apt_install("espeak-ng", "libsndfile1")
         .pip_install("torch==2.8.0", index_url="https://download.pytorch.org/whl/cpu")
         .pip_install("kokoro==0.9.4", "misaki==0.9.4", "soundfile==0.14.0",
                      "transformers==5.20.2", "huggingface-hub==2.2.0")
         .env({"HF_HOME": "/models/hf", "TOKENIZERS_PARALLELISM": "false"}))


@app.function(image=image, cpu=6, memory=16384, timeout=600, scaledown_window=2,
              volumes={"/models": cache})
def synthesize():
    import numpy as np
    import soundfile as sf
    import torch
    from huggingface_hub import snapshot_download
    from kokoro import KModel, KPipeline

    started = time.perf_counter()
    torch.set_num_threads(6)
    model_root = Path(snapshot_download("hexgrad/Kokoro-82M", revision=REVISION,
                                      allow_patterns=["config.json", "kokoro-v1_0.pth", "voices/ff_siwis.pt"]))
    cache.commit()
    model = KModel(repo_id="hexgrad/Kokoro-82M", config=str(model_root / "config.json"),
                   model=str(model_root / "kokoro-v1_0.pth")).to("cpu").eval()
    pipeline = KPipeline(lang_code="f", repo_id="hexgrad/Kokoro-82M", model=model, device="cpu")
    voice = str(model_root / "voices/ff_siwis.pt")
    clips = []
    for paragraph in PARAGRAPHS:
        audio = np.concatenate([r.audio.numpy() for r in pipeline(paragraph, voice=voice, speed=1.04)])
        data = io.BytesIO()
        sf.write(data, audio, 24000, format="WAV", subtype="PCM_16")
        clips.append({"text": paragraph, "duration_s": len(audio) / 24000,
                      "wav_base64": base64.b64encode(data.getvalue()).decode()})
    return {"clips": clips, "voice": "ff_siwis", "model": "hexgrad/Kokoro-82M", "revision": REVISION,
            "license": "Apache-2.0", "voice_credit": "SIWIS French Speech Synthesis Database (CC BY 4.0)",
            "device": "CPU", "generation_seconds": round(time.perf_counter() - started, 3)}


@app.local_entrypoint()
def main(out: str):
    output = Path(out)
    output.mkdir(parents=True, exist_ok=True)
    result = synthesize.remote()
    for index, clip in enumerate(result["clips"]):
        (output / f"vo-{index + 1}.wav").write_bytes(base64.b64decode(clip.pop("wav_base64")))
    (output / "voice-metadata.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
