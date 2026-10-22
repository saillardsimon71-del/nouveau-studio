"""Talking-head adapter — LongCat-Video-Avatar 1.5 (+ InfiniteTalk fallback).

Chosen over the older InfiniteTalk because v1.5 moved from wav2vec2 to
Whisper-large-v3 for lip sync, adds step distillation (`--use_distill`, 8 steps)
and an INT8 DiT path (`--use_int8`), and supports video continuation with a
reference image index — all of which is what a recurring presenter needs.

Input JSON keys (`prompt`, `cond_image`, `cond_audio.person1`) follow the
upstream demo assets. Flags follow the upstream README (`--stage_1 ai2v`,
`--model_type avatar-v1.5`, `--use_distill`, `--use_int8`, `--resolution`,
`--num_segments`, `--ref_img_index`, `--mask_frame_range`).

Status: adapter written, **not executed** (no GPU in this environment).
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from ..config import get_settings
from ..cost import Usage
from .base import Engine, EngineInfo, EngineOutput, EngineRequest, EngineUnavailable


class LongCatAvatarEngine(Engine):
    info = EngineInfo(
        name="longcat_avatar",
        kind="avatar",
        label="Avatar parlant — LongCat-Video-Avatar 1.5",
        capabilities=["audio_to_video", "image_to_video", "lip_sync", "long_form_continuation", "int8"],
        requires_gpu=True,
        provider=get_settings().default_provider,
        gpu="A100_80GB",
        simulated=False,
        verified=False,
        notes="Whisper-large sync, 8 pas distillés, 480p/720p. Non exécuté ici (aucun GPU).",
    )

    def __init__(self) -> None:
        self.s = get_settings()

    def available(self) -> tuple[bool, str]:
        repo = self.s.avatar_repo
        if not (repo / "run_demo_avatar_single_audio_to_video.py").exists():
            return False, f"dépôt LongCat-Video absent ({repo}) — scripts/gpu/setup_avatar.sh"
        if not self.s.avatar_weights.exists():
            return False, f"poids absents ({self.s.avatar_weights}) — scripts/gpu/download_avatar_models.sh"
        return True, ""

    def run(self, request: EngineRequest, ctx) -> EngineOutput:
        ok, reason = self.available()
        if not ok:
            raise EngineUnavailable(reason)

        reference = request.params.get("reference_image") or request.inputs.get("reference_image")
        audio = request.params.get("audio_path") or request.inputs.get("audio_path")
        if not reference or not Path(str(reference)).exists():
            raise ValueError("avatar: image de référence manquante")
        if not audio or not Path(str(audio)).exists():
            raise ValueError("avatar: piste audio manquante (générer la voix d'abord)")

        payload = {
            "prompt": request.prompt or (
                "A photorealistic presenter, mid-shot, speaking to camera in a modern studio, "
                "cinematic soft light, natural head movement and facial expression."
            ),
            "cond_image": str(reference),
            "cond_audio": {"person1": str(audio)},
        }
        input_json = request.out("avatar_input.json")
        input_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        nproc = int(request.params.get("nproc", 1))
        resolution = str(request.params.get("resolution", "720p"))
        if resolution in ("480", "720"):
            resolution += "p"
        if resolution not in ("480p", "720p"):
            raise ValueError("LongCat resolution must be 480p or 720p")
        segments = int(request.params.get("num_segments", 1))
        cmd = [
            "torchrun", f"--nproc_per_node={nproc}",
            "run_demo_avatar_single_audio_to_video.py",
            f"--context_parallel_size={nproc}",
            f"--checkpoint_dir={self.s.avatar_weights}",
            "--stage_1=ai2v",
            f"--input_json={input_json}",
            "--model_type", "avatar-v1.5",
            "--use_distill",
            "--use_int8",
            "--resolution", str(resolution),
        ]
        if segments > 1:
            cmd += [
                "--num_segments", str(segments),
                "--ref_img_index", str(int(request.params.get("ref_img_index", 10))),
                "--mask_frame_range", str(int(request.params.get("mask_frame_range", 3))),
            ]

        ctx.log(f"LongCat: {resolution}p, {segments} segment(s)", progress=0.1, stage="generate")
        log_path = request.out("engine.log")
        started = time.time()
        with log_path.open("w", encoding="utf-8") as log:
            log.write(" ".join(cmd) + "\n\n")
            log.flush()
            proc = subprocess.Popen(cmd, cwd=str(self.s.avatar_repo), stdout=log,
                                    stderr=subprocess.STDOUT, text=True)
            while proc.poll() is None:
                if _cancelled(ctx):
                    proc.terminate()
                    raise RuntimeError("job annulé")
                ctx.log("LongCat en cours", progress=min(0.9, 0.1 + (time.time() - started) / 900),
                        stage="generate")
                time.sleep(2.0)
        wall = time.time() - started
        if proc.returncode != 0:
            raise RuntimeError(f"LongCat a échoué (code {proc.returncode})\n{_tail(log_path)}")

        produced = _newest_mp4([request.output_dir, self.s.avatar_repo], since=started)
        if produced is None:
            raise RuntimeError(
                "LongCat s'est terminé sans fichier .mp4 détecté. Vérifier le chemin de sortie "
                "réel du script puis ajuster `_newest_mp4` (voir docs/STATE.md)."
            )
        out = EngineOutput(
            usage=Usage(provider=self.info.provider, gpu=self.info.gpu, gpu_seconds=wall,
                        notes=f"LongCat avatar {resolution}p"),
            notes=f"Avatar parlant généré en {wall:.0f}s",
            diagnostics={"command": cmd, "wall_s": round(wall, 1), "output": str(produced)},
        )
        out.add(produced, "video", "video/mp4", engine="longcat_avatar")
        return out


def _newest_mp4(roots: list[Path], since: float) -> Path | None:
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.mp4"):
            try:
                if path.stat().st_mtime >= since - 5:
                    candidates.append(path)
            except OSError:
                continue
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _tail(path: Path, lines: int = 20) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-lines:])
    except OSError:
        return ""


def _cancelled(ctx) -> bool:
    try:
        ctx.check_cancelled()
        return False
    except Exception:
        return True
