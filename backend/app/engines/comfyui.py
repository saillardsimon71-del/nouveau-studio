"""ComfyUI adapter (optional execution backend).

We do **not** ship invented node graphs. A workflow is exported from the ComfyUI
UI ("Save (API Format)") and dropped into `workflows/comfy/`. The adapter only:
  1. loads the JSON,
  2. substitutes placeholders (`__PROMPT__`, `__IMAGE__`, `__SEED__`,
     `__FRAMES__`, `__WIDTH__`, `__HEIGHT__`, `__FPS__`, `__AUDIO__`,
     `__OUTPUT_PREFIX__`) wherever they appear,
  3. POSTs `/prompt`, polls `/history/<id>`, downloads the result from `/view`.

This keeps the studio engine-agnostic: ComfyUI graphs are recipes, not
architecture.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings
from ..cost import Usage
from .base import Engine, EngineInfo, EngineOutput, EngineRequest, EngineUnavailable

PLACEHOLDERS = {
    "__PROMPT__": "prompt",
    "__IMAGE__": "image",
    "__AUDIO__": "audio",
    "__SEED__": "seed",
    "__FRAMES__": "num_frames",
    "__WIDTH__": "width",
    "__HEIGHT__": "height",
    "__FPS__": "fps",
}


class ComfyUIEngine(Engine):
    info = EngineInfo(
        name="comfyui",
        kind="video",
        label="ComfyUI (workflow exporté)",
        capabilities=["text_to_video", "image_to_video", "avatar", "upscale", "any_exported_graph"],
        requires_gpu=True,
        provider=get_settings().default_provider,
        gpu="RTX_5090",
        simulated=False,
        verified=False,
        notes="Backend d'exécution alternatif. Workflows à exporter depuis l'UI (voir workflows/comfy).",
    )

    def __init__(self) -> None:
        self.s = get_settings()

    def available(self) -> tuple[bool, str]:
        if not self.s.comfy_url:
            return False, "PVS_COMFY_URL non configuré"
        try:
            r = httpx.get(f"{self.s.comfy_url}/system_stats", timeout=4.0)
            if r.status_code == 200:
                return True, ""
            return False, f"ComfyUI a répondu {r.status_code}"
        except Exception as exc:
            return False, f"ComfyUI injoignable ({exc.__class__.__name__})"

    def _workflow(self, name: str, request: EngineRequest) -> dict[str, Any]:
        path = self.s.repo_root / "workflows" / "comfy" / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"workflow ComfyUI absent: {path} (exporter depuis l'UI en API format)")
        raw = json.loads(path.read_text(encoding="utf-8"))
        values = {
            key: request.params.get(key)
            for key in ("prompt", "image", "audio", "seed", "num_frames", "width", "height", "fps")
        }
        values["prompt"] = request.prompt
        values.setdefault("num_frames", round(request.duration_s * float(request.params.get("fps") or 24)))
        text = json.dumps(raw)
        for placeholder, key in PLACEHOLDERS.items():
            value = values.get(key)
            if value is None:
                continue
            replacement = json.dumps(value) if not isinstance(value, (int, float)) else str(int(value))
            text = text.replace(f'"{placeholder}"', replacement)
        return json.loads(text)

    def run(self, request: EngineRequest, ctx) -> EngineOutput:
        ok, reason = self.available()
        if not ok:
            raise EngineUnavailable(reason)
        workflow_name = str(request.params.get("workflow") or "ltx_i2v")
        graph = self._workflow(workflow_name, request)
        started = time.time()
        ctx.log(f"ComfyUI: envoi du workflow {workflow_name}", progress=0.05, stage="queue")
        with httpx.Client(base_url=self.s.comfy_url, timeout=30.0) as client:
            client_id = f"pvs-{int(started)}"
            resp = client.post("/prompt", json={"prompt": graph, "client_id": client_id})
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
            while True:
                if _cancelled(ctx):
                    client.post("/interrupt")
                    raise RuntimeError("job annulé")
                history = client.get(f"/history/{prompt_id}").json()
                entry = history.get(prompt_id)
                if entry:
                    status = entry.get("status", {})
                    if status.get("status_str") == "error":
                        raise RuntimeError(f"ComfyUI erreur: {status}")
                    if status.get("completed", True):
                        break
                elapsed = time.time() - started
                ctx.log("ComfyUI en cours", progress=min(0.9, 0.05 + elapsed / 600), stage="generate")
                time.sleep(2.0)
            files = _collect_outputs(entry)
            if not files:
                raise RuntimeError("ComfyUI: aucun fichier de sortie dans l'historique")
            saved: list[Path] = []
            for index, item in enumerate(files):
                params = {"filename": item["filename"], "subfolder": item.get("subfolder", ""), "type": item.get("type", "output")}
                data = client.get("/view", params=params).content
                target = request.out(f"comfy_{index}{Path(item['filename']).suffix or '.mp4'}")
                target.write_bytes(data)
                saved.append(target)
        wall = time.time() - started
        out = EngineOutput(
            usage=Usage(provider=self.info.provider, gpu=self.info.gpu, gpu_seconds=wall, notes="ComfyUI"),
            notes=f"ComfyUI ({workflow_name}) — {wall:.0f}s",
            diagnostics={"workflow": workflow_name, "prompt_id": prompt_id},
        )
        for path in saved:
            kind = "image" if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else "video"
            mime = "image/png" if kind == "image" else "video/mp4"
            out.add(path, kind, mime, engine="comfyui")
        return out


def _collect_outputs(entry: dict[str, Any]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for node in (entry.get("outputs") or {}).values():
        for key in ("videos", "gifs", "images"):
            for item in node.get(key, []) or []:
                if item.get("filename"):
                    files.append(item)
    return files


def _cancelled(ctx) -> bool:
    try:
        ctx.check_cancelled()
        return False
    except Exception:
        return True
