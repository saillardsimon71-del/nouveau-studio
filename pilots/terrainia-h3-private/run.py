"""Run one approved private H3 comparison and encrypt the result before upload."""
import base64
import io
import json
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image
import modal
import imageio_ffmpeg

from worker import app, render_comparison

TRANSPORT = "terrainia-h3-pilot-20261113-transport"
ROOT = Path(__file__).resolve().parent
OUT = Path("build/h3-private")
GUIDE_HASHES = {
    "first": "fe32eb2adfb54701e5fe287c2dc95bb21954215f1e55044acf72699ef99d5170",
    "last": "7fc6f3b588f1c4ffc0c4dc83a54caefb699d5016effa408fb33db02169998be1",
}


def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def load_inputs():
    transport = modal.Dict.from_name(TRANSPORT, environment_name="main")
    pkey = serialization.load_pem_private_key(transport["private_key"], password=None)
    encrypted = (ROOT / "input.encrypted").read_bytes()
    key = pkey.decrypt(encrypted[:256], oaep())
    payload = json.loads(AESGCM(key).decrypt(encrypted[256:268], encrypted[268:], b"terrainia-h3-pilot/input/v1"))
    guides = []
    for name, expected in GUIDE_HASHES.items():
        raw = base64.b64decode(payload[name], validate=True)
        if sha256(raw).hexdigest() != expected:
            raise ValueError("Guide digest mismatch")
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        if image.size != (576, 1024):
            raise ValueError("Guide dimensions changed")
        png = io.BytesIO()
        image.save(png, format="PNG")
        guides.append(png.getvalue())
    return guides, payload["prompt"], serialization.load_pem_public_key(payload["output_public_key"].encode())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    guides, prompt, recipient = load_inputs()
    print("H3_TWO_GUIDES_VERIFIED", flush=True)
    start = time.monotonic()
    with modal.enable_output(), app.run(name="terrainia-rust-h3-fl2va-private", environment_name="main"):
        call = render_comparison.spawn(*guides, prompt)
        print("H3_GPU_SUBMITTED", flush=True)
        try:
            raw, receipt = call.get(timeout=1200)
        except BaseException:
            call.cancel(terminate_containers=True)
            raise
    receipt.update({"wall_seconds": round(time.monotonic() - start, 2), "guide_sha256": GUIDE_HASHES})
    print("H3_GPU_DONE", json.dumps(receipt), flush=True)
    # The native take has 107 frames; keep the entire gesture and both anchors while
    # standardizing to the 105-frame silent comparison cut. Preserve native AV too.
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    native = Path("/tmp/terrainia-h3-native.mp4")
    master = Path("/tmp/terrainia-h3-master.mp4")
    native.write_bytes(raw)
    try:
        subprocess.run([ffmpeg, "-v", "error", "-xerror", "-y", "-i", str(native), "-an", "-vf",
                        "scale=1080:1920:flags=lanczos,setsar=1,settb=AVTB,setpts=(104/106)*PTS,fps=24,tpad=stop_mode=clone:stop=2",
                        "-frames:v", "105", "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(master)], check=True, timeout=60)
        subprocess.run([ffmpeg, "-v", "error", "-xerror", "-i", str(master), "-f", "null", "-"], check=True, timeout=45)
        result = master.read_bytes()
        receipt["master_sha256"] = sha256(result).hexdigest()
        from zipfile import ZipFile
        archive = io.BytesIO()
        with ZipFile(archive, "w") as z:
            z.writestr("TerrainIA-Rouille-H3-FL2VA.mp4", result)
            z.writestr("native.mp4", raw)
            z.writestr("receipt.json", json.dumps(receipt, indent=2))
        key, nonce = os.urandom(32), os.urandom(12)
        encrypted = AESGCM(key).encrypt(nonce, archive.getvalue(), b"terrainia-h3-pilot/output/v1")
        (OUT / "result.encrypted").write_bytes(recipient.encrypt(key, oaep()) + nonce + encrypted)
        print("H3_ENCRYPTED_RESULT_READY", flush=True)
    finally:
        native.unlink(missing_ok=True)
        master.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
