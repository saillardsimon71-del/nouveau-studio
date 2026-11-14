"""One private H3 audio-guided comparison, returning silent video only."""
import base64, hashlib, io, json, os, subprocess, tempfile
import imageio_ffmpeg
from pathlib import Path
from zipfile import ZipFile
import modal
from PIL import Image
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from worker import app,render_comparison

ROOT=Path(__file__).resolve().parent
def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None)
def check(data,digest):
    if hashlib.sha256(data).hexdigest()!=digest:
        raise ValueError("Guide hash mismatch")
def main():
    d=modal.Dict.from_name("terrainia-noe-h3-guide-20261114",environment_name="main")
    key=serialization.load_pem_private_key(d["private_key"],password=None)
    blob=(ROOT/"input.encrypted").read_bytes()
    data=json.loads(AESGCM(key.decrypt(blob[:256],oaep())).decrypt(blob[256:268],blob[268:],b"noe-h3-input/v1"))
    image=base64.b64decode(data["portrait"],validate=True)
    audio=base64.b64decode(data["guide"],validate=True)
    check(image,"c36c7c45191e0e7411f4be131325dc0d2aa97dba788410334995b1b8ee252743")
    check(audio,"8542e2ff83235c0c324634f0ed64a79ef4aea85cea389a33537b6028651d95a0")
    png=io.BytesIO()
    with Image.open(io.BytesIO(image)) as im:
        im.convert("RGB").save(png,format="PNG")
    prompt=("A locked medium-wide, single camera YouTube presenter shot in the exact same studio as the first frame. "
            "The same fictional young adult man at the same desk speaks directly to the lens in French, synchronized to the supplied speech guide from frame zero. "
            "Keep face, dark crewneck, desk, hands, set, lighting and framing consistent. He speaks conversationally with relaxed eyelids, natural mouth closure, small asymmetrical eyebrow movements and subtle blinks. "
            "No camera movement, no cuts, no overlays, no on-screen text, no extra people. Hands stay low and quiet. No exaggerated nodding.")
    with modal.enable_output(),app.run(name="terrainia-noe-native-h3-audio-guide",environment_name="main"):
        call=render_comparison.spawn(png.getvalue(),audio,prompt)
        print("NOE_H3_AUDIO_GUIDED_GPU_SUBMITTED",flush=True)
        try:
            raw,receipt=call.get(timeout=1200)
        except BaseException:
            call.cancel(terminate_containers=True)
            raise
    check(raw,receipt["raw_sha256"])
    check(audio,receipt["audio_guide_sha256"])
    with tempfile.TemporaryDirectory() as td:
        src,dest=Path(td)/"native.mp4",Path(td)/"picture.mp4"
        src.write_bytes(raw)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),"-v","error","-y","-i",str(src),
                        "-map","0:v:0","-an","-c:v","copy",str(dest)],check=True,timeout=60)
        raw=dest.read_bytes()
    receipt["silent_sha256"]=hashlib.sha256(raw).hexdigest()
    archive=io.BytesIO()
    with ZipFile(archive,"w") as z:
        z.writestr("h3-presenter.mp4",raw)
        z.writestr("receipt.json",json.dumps(receipt,indent=2))
    out=Path("build/noe-h3-result.encrypted")
    out.parent.mkdir(exist_ok=True)
    recipient=serialization.load_pem_public_key(data["output_public_key"].encode())
    key=os.urandom(32)
    nonce=os.urandom(12)
    out.write_bytes(recipient.encrypt(key,oaep())+nonce+AESGCM(key).encrypt(nonce,archive.getvalue(),b"noe-h3-output/v1"))
    print("NOE_H3_AUDIO_GUIDED_RESULT_READY",receipt["gpu_worker_seconds"],flush=True)
if __name__=="__main__":
    main()
