"""French voice generation adapters.

Two candidates, both French-capable, both zero-shot from a short reference:

* Chatterbox Multilingual V3 (Resemble AI) — 23+ languages, `exaggeration`
  control for delivery, MIT-licensed weights. **Default**: smallest model that
  keeps a cloned voice consistent across a whole ad.
* VoxCPM2 (OpenBMB) — 2B, 30 languages, 48 kHz output, ~8 GB VRAM, publishes
  French intelligibility numbers. **Alternative** when audio quality matters more
  than latency.

IndexTTS-2.5 was reviewed and rejected for this use case: it ships Chinese,
English, Japanese, Spanish and Arabic — no French.

Execution happens through `scripts/gpu/tts_generate.py` so the studio process
never needs the model stack installed. Status: adapters written, not executed
here (weights unavailable in this sandbox).
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from ..config import _env, get_settings
from ..cost import Usage
from .base import Engine, EngineInfo, EngineOutput, EngineRequest, EngineUnavailable


class _LocalVoiceEngine(Engine):
    engine_id = "chatterbox"
    script = "tts_chatterbox.py"

    def __init__(self) -> None:
        self.s = get_settings()

    @property
    def script_path(self) -> Path:
        return self.s.repo_root / "scripts" / "gpu" / self.script

    # the import check costs a few seconds (torch); cached briefly
    _check_cache: dict[str, tuple[float, bool, str]] = {}

    def available(self) -> tuple[bool, str]:
        if not self.script_path.exists():
            return False, f"script manquant: {self.script_path}"
        python = Path(self.s.tts_python)
        if "/" in self.s.tts_python and not python.exists():
            return False, f"interpréteur Python absent: {self.s.tts_python}"
        if "/" not in self.s.tts_python and shutil.which(self.s.tts_python) is None:
            return False, f"interpréteur Python introuvable: {self.s.tts_python}"
        if _env("PVS_SKIP_ENGINE_CHECK", "") in {"1", "true"}:
            return True, ""
        now = time.time()
        cached = self._check_cache.get(self.engine_id)
        if cached and now - cached[0] < 120:
            return cached[1], cached[2]
        try:
            proc = subprocess.run(
                [self.s.tts_python, str(self.script_path), "--check"],
                capture_output=True, text=True, timeout=120,
            )
            ok = proc.returncode == 0
            reason = "" if ok else (proc.stderr or proc.stdout or "modèle indisponible").strip().splitlines()[-1]
        except Exception as exc:  # pragma: no cover
            ok, reason = False, f"vérification impossible ({exc.__class__.__name__})"
        self._check_cache[self.engine_id] = (now, ok, reason)
        return ok, reason

    def _cmd(self, request: EngineRequest, out_path: Path) -> list[str]:
        text = str(request.params.get("text") or request.shot.get("dialogue") or "").strip()
        if not text:
            raise ValueError("tts: texte vide")
        cmd = [
            self.s.tts_python, str(self.script_path),
            "--text", text,
            "--out", str(out_path),
            "--language", str(request.params.get("language") or "fr"),
        ]
        ref = request.params.get("ref_audio") or request.inputs.get("ref_audio")
        if ref:
            cmd += ["--speaker-wav", str(ref)]
        controls = ("cfg_weight", "model") if self.engine_id == "voxcpm2" else (
            "exaggeration", "cfg_weight", "temperature", "model"
        )
        for key in controls:
            if key in request.params and request.params[key] is not None:
                cmd += [f"--{key.replace('_', '-')}", str(request.params[key])]
        if self.engine_id == 'chatterbox' and request.params.get('model_dir'):
            cmd += ['--model-dir', str(request.params['model_dir'])]
        return cmd

    def run(self, request: EngineRequest, ctx) -> EngineOutput:
        ok, reason = self.available()
        if not ok:
            raise EngineUnavailable(reason)
        out_path = request.out("voice.wav")
        cmd = self._cmd(request, out_path)
        ctx.log(f"Synthèse vocale ({self.engine_id})", progress=0.2, stage="tts")
        log_path = request.out("engine.log")
        started = time.time()
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            log.write(proc.stdout + "\n" + proc.stderr)
        wall = time.time() - started
        if proc.returncode != 0 or not out_path.exists():
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
            raise RuntimeError(f"TTS a échoué ({proc.returncode})\n{tail}")
        from .. import media

        info = media.probe(out_path)
        out = EngineOutput(
            usage=Usage(provider="local", gpu="RTX_4090", gpu_seconds=wall, notes=f"TTS {self.engine_id}"),
            notes=f"Voix {self.engine_id} — {info.duration_s:.1f}s",
            diagnostics={"command": cmd, "wall_s": round(wall, 1), "duration_s": info.duration_s},
        )
        out.add(out_path, "audio", "audio/wav", engine=self.engine_id, duration_s=info.duration_s)
        return out


class ChatterboxEngine(_LocalVoiceEngine):
    engine_id = "chatterbox"
    script = "tts_chatterbox.py"
    info = EngineInfo(
        name="chatterbox",
        kind="tts",
        label="Voix française — Chatterbox Multilingual V3",
        capabilities=["tts", "voice_clone", "french", "emotion_control"],
        requires_gpu=False,
        provider="local",
        gpu="RTX_4090",
        simulated=False,
        verified=False,
        notes="23+ langues, clonage 5s, contrôle d'exagération. Non exécuté ici.",
    )


class VoxCPMEngine(_LocalVoiceEngine):
    engine_id = "voxcpm2"
    script = "tts_voxcpm.py"
    info = EngineInfo(
        name="voxcpm2",
        kind="tts",
        label="Voix française — VoxCPM2 (48 kHz)",
        capabilities=["tts", "voice_clone", "french", "48khz", "voice_design"],
        requires_gpu=True,
        provider="local",
        gpu="RTX_4090",
        simulated=False,
        verified=False,
        notes="Alternative haut de gamme audio. ~8 Go VRAM, RTF ~0.3 sur 4090. Non exécuté ici.",
    )
