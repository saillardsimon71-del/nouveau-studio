import json
import subprocess
import tempfile
import time
from pathlib import Path

import modal

app = modal.App('pvs-human-performance-voice')
volume = modal.Volume.from_name('pvs-commercial-audio-models')
image = (modal.Image.debian_slim(python_version='3.11')
         .apt_install('git', 'ffmpeg', 'libsndfile1')
         .pip_install('torch==2.6.0', 'torchaudio==2.6.0', index_url='https://download.pytorch.org/whl/cpu')
         .pip_install('git+https://github.com/resemble-ai/chatterbox.git@5de7a54aa4e5e2baadb0182dde554908b48b85c2')
         .env({'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HOME': '/tmp/hf'})
         .add_local_file(Path(__file__).resolve().parents[1] / 'gpu/tts_chatterbox.py', '/opt/tts_chatterbox.py'))


@app.function(image=image, cpu=8, memory=16384, timeout=1200, max_containers=1, scaledown_window=2,
              volumes={'/models': volume.with_mount_options(read_only=True)})
def synthesize(reference_wav: bytes, text: str):
    required = ('t3_mtl23ls_v3.safetensors', 's3gen.pt', 've.pt', 'grapheme_mtl_merged_expanded_v1.json')
    root = Path('/models/compare/chat')
    if not all((root / name).is_file() for name in required):
        raise ValueError('Existing Chatterbox V3 weights incomplete; no download permitted')
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        reference = folder / 'reference.wav'
        reference.write_bytes(reference_wav)
        output = folder / 'voice.wav'
        subprocess.run(['python', '/opt/tts_chatterbox.py', '--model-dir', str(root), '--model', 'v3',
                        '--speaker-wav', str(reference), '--text', text, '--language', 'fr', '--out', str(output)],
                       check=True, timeout=1000)
        return {'wav': output.read_bytes(), 'engine': 'chatterbox-v3', 'device': 'cpu',
                'seconds': round(time.monotonic() - started, 2), 'source': 'synthetic_from_user_reference',
                'upstream_revision': '5de7a54aa4e5e2baadb0182dde554908b48b85c2'}


@app.local_entrypoint()
def main(reference_wav: str, out: str, text: str):
    result = synthesize.remote(Path(reference_wav).read_bytes(), text)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result.pop('wav'))
    target.with_suffix('.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
