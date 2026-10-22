"""LTX-2.5 adapter (native `ltx_pipelines` CLI).

Flags below were taken from the upstream source (`packages/ltx-pipelines/src/
ltx_pipelines/utils/args.py`, `retake.py`) at the time of writing, not invented:
`--transformer-path`, `--text-encoder-path`, `--video-vae-path`, `--audio-vae-path`,
`--spatial-upsampler-path`, `--detailing-lora`, `--num-frames`, `--width`,
`--height`, `--frame-rate`, `--seed`, `--prompt`, `--output-path`, `--image PATH
FRAME STRENGTH`, `--quantization`, `--offload`, and for retake `--video-path
--start-time --end-time`.

Status: adapter written, **not yet executed on a GPU** (this environment has no
CUDA device). See docs/STATE.md.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from ..config import get_settings
from ..cost import Usage
from .base import Engine, EngineInfo, EngineOutput, EngineRequest, EngineUnavailable

PIPELINES = {
    "distilled": ("ltx_pipelines.distilled", "rapide, 8+4 pas"),
    "dfr": ("ltx_pipelines.dfr_pipeline", "qualité production (DFR)"),
    "two_stages": ("ltx_pipelines.ti2vid_two_stages", "guidé deux étapes (CFG/STG)"),
}


class LTXNativeEngine(Engine):
    info = EngineInfo(
        name="ltx_native",
        kind="video",
        label="LTX-2.5 (pipelines natives)",
        capabilities=["text_to_video", "image_to_video", "audio_video_joint", "retake_region", "4k", "lora_style"],
        requires_gpu=True,
        provider=get_settings().default_provider,
        gpu="H100_80GB",
        simulated=False,
        verified=False,
        notes="Moteur principal image->vidéo. Non exécuté dans cet environnement (aucun GPU).",
    )

    def __init__(self) -> None:
        self.s = get_settings()

    # --- availability -----------------------------------------------------------
    def model_paths(self) -> dict[str, Path]:
        m = self.s.ltx_models
        return {
            "transformer": m / "diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors",
            "text_encoder": m / "text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors",
            "video_vae": m / "vae/ltx-2.5-video-vae-bf16.safetensors",
            "audio_vae": m / "vae/ltx-2.5-audio-vae-bf16.safetensors",
            "upsampler": m / "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
            "detailing_lora": m / "loras/ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors",
        }

    def available(self) -> tuple[bool, str]:
        if not (self.s.ltx_repo / "packages" / "ltx-pipelines").exists():
            return False, f"dépôt LTX-2 absent ({self.s.ltx_repo}) — script scripts/gpu/setup_ltx.sh"
        missing = [name for name, p in self.model_paths().items() if not p.exists() and name != "detailing_lora"]
        if missing:
            return False, f"poids manquants: {', '.join(missing)} (scripts/gpu/download_ltx_models.sh)"
        return True, ""

    # --- command ----------------------------------------------------------------
    def build_command(self, request: EngineRequest, out_path: Path) -> tuple[list[str], str]:
        pipeline = str(request.params.get("pipeline") or self.s.ltx_default_pipeline)
        if pipeline not in PIPELINES:
            raise ValueError(f"pipeline inconnu: {pipeline} ({', '.join(PIPELINES)})")
        module, _ = PIPELINES[pipeline]
        paths = self.model_paths()
        fps = int(request.params.get("fps") or 24)
        frames = int(request.params.get("num_frames") or round(request.duration_s * fps))
        frames = max(9, ((frames - 1) // 8) * 8 + 1)  # causal grid 8k+1
        width = int(request.params.get("width") or 1080)
        height = int(request.params.get("height") or 1920)
        if (width * height) % 128:  # keep dimensions on the model's grid
            width, height = 1088, 1920

        cmd = [
            self.s.ltx_python, "-m", module,
            "--transformer-path", str(paths["transformer"]),
            "--text-encoder-path", str(paths["text_encoder"]),
            "--video-vae-path", str(paths["video_vae"]),
            "--audio-vae-path", str(paths["audio_vae"]),
            "--spatial-upsampler-path", str(paths["upsampler"]),
            "--num-frames", str(frames),
            "--width", str(width),
            "--height", str(height),
            "--frame-rate", str(fps),
            "--seed", str(int(request.params.get("seed") or 42)),
            "--prompt", request.prompt,
            "--output-path", str(out_path),
        ]
        if pipeline == "dfr" and paths["detailing_lora"].exists():
            cmd += ["--detailing-lora", str(paths["detailing_lora"])]
        if pipeline == "dfr" and request.params.get("temporal_upscalings"):
            cmd += ["--temporal-upscalings", str(int(request.params["temporal_upscalings"]))]
        if request.params.get("quantization"):
            cmd += ["--quantization", str(request.params["quantization"])]
        else:
            cmd += ["--quantization", "fp8-cast"]
        if request.params.get("offload"):
            cmd += ["--offload", str(request.params["offload"])]
        for lora in request.params.get("loras", []) or []:
            cmd += ["--lora", str(lora)]
        image = request.params.get("start_image") or request.inputs.get("start_image")
        if image:
            cmd += ["--image", str(image), "0", str(float(request.params.get("image_strength", 1.0)))]
        end_image = request.params.get("end_image")
        if end_image:
            cmd += ["--image", str(end_image), str(frames - 1), "1.0"]
        return cmd, pipeline

    # --- execution --------------------------------------------------------------
    def _run_subprocess(self, cmd: list[str], request: EngineRequest, ctx, out_path: Path) -> None:
        ctx.log("LTX: " + " ".join(cmd[:3]) + " …", progress=0.1, stage="generate")
        log_path = request.out("engine.log")
        started = time.time()
        with log_path.open("w", encoding="utf-8") as log:
            log.write(" ".join(cmd) + "\n\n")
            log.flush()
            proc = subprocess.Popen(
                cmd, cwd=str(self.s.ltx_repo), stdout=log, stderr=subprocess.STDOUT, text=True,
            )
            while proc.poll() is None:
                if _cancelled(ctx):
                    proc.terminate()
                    raise RuntimeError("job annulé")
                elapsed = time.time() - started
                ctx.log("LTX en cours", progress=min(0.9, 0.1 + elapsed / 600), stage="generate")
                time.sleep(2.0)
        if proc.returncode != 0 or not out_path.exists():
            tail = _tail(log_path)
            raise RuntimeError(f"LTX a échoué (code {proc.returncode})\n{tail}")

    def run(self, request: EngineRequest, ctx) -> EngineOutput:
        ok, reason = self.available()
        if not ok:
            raise EngineUnavailable(reason)
        out_path = request.out("ltx.mp4")
        cmd, pipeline = self.build_command(request, out_path)
        started = time.time()
        self._run_subprocess(cmd, request, ctx, out_path)
        wall = time.time() - started
        out = EngineOutput(
            usage=Usage(provider=self.info.provider, gpu=self.info.gpu, gpu_seconds=wall,
                        notes=f"LTX-2.5 {pipeline}, {request.duration_s:.1f}s"),
            notes=f"LTX-2.5 ({pipeline}) — {wall:.0f}s de GPU",
            diagnostics={"pipeline": pipeline, "command": cmd, "wall_s": round(wall, 1)},
        )
        out.add(out_path, "video", "video/mp4", engine="ltx_native", pipeline=pipeline)
        return out

    def run_retake(self, request: EngineRequest, ctx) -> EngineOutput:
        """Regenerate only [start_s, end_s) of an existing clip (LTX RetakePipeline)."""
        ok, reason = self.available()
        if not ok:
            raise EngineUnavailable(reason)
        source = Path(str(request.params["video_path"]))
        out_path = request.out("retake.mp4")
        cmd = [
            self.s.ltx_python, "-m", "ltx_pipelines.retake",
            "--video-path", str(source),
            "--start-time", str(float(request.params["start_s"])),
            "--end-time", str(float(request.params["end_s"])),
            "--prompt", request.prompt,
            "--seed", str(int(request.params.get("seed") or 7)),
            "--output-path", str(out_path),
        ]
        started = time.time()
        self._run_subprocess(cmd, request, ctx, out_path)
        wall = time.time() - started
        out = EngineOutput(
            usage=Usage(provider=self.info.provider, gpu=self.info.gpu, gpu_seconds=wall, notes="LTX retake"),
            notes=f"Retake {request.params['start_s']}→{request.params['end_s']}s",
            diagnostics={"command": cmd},
        )
        out.add(out_path, "video", "video/mp4", engine="ltx_native", retake=True)
        return out


def _tail(path: Path, lines: int = 15) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        return "\n".join(content[-lines:])
    except OSError:
        return ""


def _cancelled(ctx) -> bool:
    try:
        ctx.check_cancelled()
        return False
    except Exception:
        return True
