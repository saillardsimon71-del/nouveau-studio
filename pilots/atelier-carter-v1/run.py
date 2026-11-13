"""Run the single carter ASMR test and encrypt the result before upload."""
import base64
import io
import json
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import time
import tempfile
from zipfile import ZipFile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image
import modal
import imageio_ffmpeg

from worker import app, render_pilot

TRANSPORT = "terrainia-h3-pilot-20261113-transport"
ROOT = Path(__file__).resolve().parent
OUT = Path("build/atelier-carter")
EXPECTED_SHA = "20757ae06c21d53a5dd7c4a563f5dea63aec44a345739e7451ab0a76054e452b"
SEEDS = [128023]


def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def load_inputs():
    transport = modal.Dict.from_name(TRANSPORT, environment_name="main")
    pkey = serialization.load_pem_private_key(transport["private_key"], password=None)
    encrypted = (ROOT / "input.encrypted").read_bytes()
    key = pkey.decrypt(encrypted[:256], oaep())
    payload = json.loads(AESGCM(key).decrypt(encrypted[256:268], encrypted[268:], b"atelier-impossible/input/v1"))
    guide = base64.b64decode(payload.pop("guide"), validate=True)
    if sha256(guide).hexdigest() != EXPECTED_SHA or payload["guide_sha256"] != EXPECTED_SHA:
        raise ValueError("Guide digest mismatch")
    if payload["seed_list"] != SEEDS or [payload[k] for k in ("width","height","frames","fps","steps")] != [576,1024,124,24,20]:
        raise ValueError("Pilot recipe mismatch")
    image = Image.open(io.BytesIO(guide)).convert("RGB")
    if image.size != (576,1024):
        raise ValueError("Guide dimensions changed")
    png = io.BytesIO()
    image.save(png, format="PNG")
    recipient = serialization.load_pem_public_key(payload.pop("output_public_key").encode())
    return guide, png.getvalue(), payload, recipient


def encrypt_result(archive, recipient):
    key, nonce = os.urandom(32), os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, archive.getvalue(), b"atelier-impossible/output/v1")
    (OUT / "result.encrypted").write_bytes(recipient.encrypt(key, oaep()) + nonce + encrypted)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jpeg, guide, recipe, recipient = load_inputs()
    archive = io.BytesIO()
    results = []
    failure = None
    start = time.monotonic()
    print("ATELIER_START_IMAGE_VERIFIED", flush=True)
    with ZipFile(archive, "w") as z:
        z.writestr("start.jpg", jpeg)
        z.writestr("recipe.json", json.dumps(recipe, indent=2, ensure_ascii=False))
        try:
            with modal.enable_output(), app.run(name="terrainia-atelier-impossible-v1", environment_name="main"):
                for i, (raw, receipt) in enumerate(render_pilot.remote_gen(guide, recipe["prompt"], SEEDS), start=1):
                    if i > len(SEEDS) or receipt["seed"] != SEEDS[i-1] or sha256(raw).hexdigest() != receipt["raw_sha256"]:
                        raise ValueError("Unexpected render receipt")
                    # No cut or retiming. Preserve generated AAC audio bit-for-bit.
                    with tempfile.TemporaryDirectory() as tmp:
                        native, master = Path(tmp)/"native.mp4", Path(tmp)/"master.mp4"
                        native.write_bytes(raw)
                        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                        subprocess.run([ffmpeg,"-v","error","-xerror","-y","-i",str(native),"-map","0:v:0","-map","0:a:0",
                                        "-vf","scale=1080:1920:flags=lanczos,setsar=1","-c:v","libx264","-preset","fast",
                                        "-crf","17","-pix_fmt","yuv420p","-c:a","copy","-movflags","+faststart",str(master)],
                                       check=True,timeout=60)
                        subprocess.run([ffmpeg,"-v","error","-xerror","-i",str(master),"-f","null","-"],check=True,timeout=50)
                        clip = master.read_bytes()
                    name = "TerrainIA-Atelier-Carter-Moto.mp4"
                    z.writestr(name, clip)
                    receipt.update({"file": name, "master_sha256": sha256(clip).hexdigest(), "guide_sha256": EXPECTED_SHA})
                    results.append(receipt)
                    print("ATELIER_CLIP_DONE",json.dumps(receipt),flush=True)
        except Exception as exc:
            failure = type(exc).__name__
        z.writestr("receipt.json",json.dumps({"results":results,"failure":failure,"wall_seconds":round(time.monotonic()-start,2)},indent=2))
    if results:
        encrypt_result(archive, recipient)
    if len(results) != len(SEEDS):
        raise RuntimeError(f"Pilot incomplete: {len(results)}/{len(SEEDS)} verified clips ({failure})") from None


if __name__ == "__main__":
    main()
