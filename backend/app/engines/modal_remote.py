import base64
import json
import os
import time
from pathlib import Path

from .. import media
from ..avatar import plan_audio
from ..config import _env_flag
from ..cost import Usage
from .base import Engine, EngineInfo, EngineOutput


class ModalEngine(Engine):
    def __init__(self, kind):
        self.kind = kind
        self.app_name = os.environ.get('PVS_MODAL_AVATAR_APP', 'pvs-longcat-avatar') if kind == 'avatar' else 'pvs-ltx'
        self.function_name = "render_avatar" if kind == "avatar" else "render_clip"
        self.info = EngineInfo(
            name="modal_avatar" if kind == "avatar" else "modal_ltx", kind=kind,
            label="LongCat 1.5 sur Modal" if kind == "avatar" else "LTX-2.5 sur Modal",
            capabilities=["image_to_video", "lip_sync"] if kind == "avatar" else ["text_to_video", "image_to_video"],
            requires_gpu=True, provider="modal", gpu="A100_80GB" if kind == "avatar" else "L40S",
            verified=True,
            notes=('Voix validée, maximum ' + ('6.92 s' if os.environ.get('PVS_MODAL_AVATAR_MAX_SEGMENTS') == '2' else '3.72 s'))
            if kind == 'avatar' else 'Rendu distant sans GitHub Actions',
        )

    def function(self):
        import modal

        workspace = modal.Workspace.from_context().hydrate().name
        if workspace != "kulejean567":
            raise ValueError("Le studio attend le workspace Modal kulejean567")
        return modal.Function.from_name(self.app_name, self.function_name, environment_name="main").hydrate()

    def available(self):
        if not _env_flag("PVS_MODAL_ENABLED", False):
            return False, "Activer PVS_MODAL_ENABLED sur le serveur du studio"
        try:
            self.function()
            return True, ""
        except Exception as exc:
            return False, f"Connexion Modal indisponible ({type(exc).__name__})"

    def payload(self, request):
        if self.kind == "avatar":
            audio = Path(request.inputs.get("audio_path") or request.params.get("audio_path") or "")
            if not audio.is_file():
                raise ValueError("Avatar: piste audio manquante")
            duration = media.probe(audio).duration_s
            plan = plan_audio(duration, max_segments=int(os.environ.get('PVS_MODAL_AVATAR_MAX_SEGMENTS', '1')))
            reference = request.inputs.get("reference_image") or request.params.get("reference_image")
            if not reference or not Path(reference).is_file():
                raise ValueError("Avatar: sélectionner un personnage avec une image de référence")
            png = request.out("reference.png")
            media.run_ffmpeg(["-i", str(reference), "-frames:v", "1", str(png)])
            args = (base64.b64encode(png.read_bytes()).decode(), base64.b64encode(audio.read_bytes()).decode(), request.prompt)
            return (*args, 2) if plan['num_segments'] == 2 else args
        payload = {
            "prompt": request.prompt, "duration_s": request.duration_s,
            "aspect_ratio": request.project.get("format", "9:16"),
            "seed": request.params.get("seed", 42), "audio_mode": request.params.get("audio_mode", "native"),
        }
        reference = request.inputs.get("reference_image") or request.params.get("reference_image")
        if reference:
            png = request.out("reference.png")
            media.run_ffmpeg(["-i", str(reference), "-frames:v", "1", str(png)])
            payload["image_png_base64"] = base64.b64encode(png.read_bytes()).decode()
        if not 1 <= request.duration_s <= 15:
            raise ValueError("LTX accepte des plans de 1 à 15 secondes")
        return (payload,)

    def save_result(self, request, result):
        path = request.out("modal_avatar.mp4" if self.kind == "avatar" else "modal_ltx.mp4")
        key = "video_b64" if self.kind == "avatar" else "video_base64"
        path.write_bytes(base64.b64decode(result[key], validate=True))
        info = media.probe(path)
        if not info.width or info.duration_s <= 0:
            raise ValueError("Modal n'a pas retourné une vidéo lisible")
        if self.kind == "avatar" and (not info.has_audio or info.width * 16 != info.height * 9):
            raise ValueError("Avatar Modal: piste audio ou format vertical 9:16 manquant")
        metadata = result["metadata"]
        request.out("modal_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        seconds = float(metadata.get("gpu_wall_seconds", metadata.get("generation_seconds", 0)))
        rate = (0.000694 if self.kind == "avatar" else 0.000542) + 8 * 0.0000131 + 64 * 0.00000222
        out = EngineOutput(
            usage=Usage(provider="modal", gpu=self.info.gpu, gpu_seconds=seconds, rate_usd_hr=rate * 3600,
                        notes="Estimation GPU + CPU/RAM réservés, hors démarrage et stockage"),
            diagnostics=metadata,
        )
        out.add(path, "video", "video/mp4", engine=self.info.name, simulated=False)
        return out

    def run(self, request, ctx):
        payload = self.payload(request)
        ctx.check_cancelled()
        call = self.function().spawn(*payload)
        request.out("modal_call.json").write_text(json.dumps({"call_id": call.object_id, "app": self.app_name}), encoding="utf-8")
        complete = False
        started = time.monotonic()
        try:
            while True:
                ctx.check_cancelled()
                if time.monotonic() - started > 2100:
                    raise TimeoutError("Modal: délai maximal de rendu dépassé")
                ctx.log("Rendu Modal en cours", progress=0.25, stage="generate")
                try:
                    result = call.get(timeout=5)
                    complete = True
                    return self.save_result(request, result)
                except TimeoutError:
                    continue
        finally:
            if not complete:
                call.cancel(terminate_containers=True)


class ModalH3Engine(ModalEngine):
    """MiniMax H3 on our own Modal GPU, same request/artifact contract as LTX.

    An unavailable deployment remains explicitly unavailable, so the existing
    video resolver can fall back to LTX without pretending to have run H3.
    """

    def __init__(self):
        super().__init__("video")
        self.app_name = "pvs-minimax-h3"
        self.function_name = "render_clip"
        self.info = EngineInfo(
            name="modal_h3", kind="video",
            label="MiniMax H3 — Modal (poids locaux, sans API)",
            capabilities=["text_to_video", "image_to_video", "audio_video_joint"],
            requires_gpu=True, provider="modal", gpu="L40S",
            verified=False,
            notes="H3 FL2VA sur ComfyUI; 4 à 15 s, 24fps; contrôles visuels requis",
        )

    def payload(self, request):
        if not 4 <= request.duration_s <= 15:
            raise ValueError("MiniMax H3 accepte des plans de 4 à 15 secondes")
        payload = super().payload(request)[0]
        payload["steps"] = int(request.params.get("steps", 20))
        if not 1 <= payload["steps"] <= 35:
            raise ValueError("MiniMax H3 steps hors intervalle 1..35")
        return (payload,)

    def save_result(self, request, result):
        # Do not claim an LTX render in filenames, usage, or engine metadata.
        path = request.out("modal_h3.mp4")
        path.write_bytes(base64.b64decode(result["video_base64"], validate=True))
        info = media.probe(path)
        if not info.width or info.duration_s <= 0:
            raise ValueError("Modal H3 n'a pas retourné un MP4 lisible")
        metadata = result.get("metadata", {})
        request.out("modal_h3_metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8")
        seconds = float(metadata.get("generation_seconds", 0))
        rate_per_second = 0.000542 + 8 * 0.0000131 + 64 * 0.00000222
        output = EngineOutput(
            usage=Usage(provider="modal", gpu="L40S", gpu_seconds=seconds,
                        rate_usd_hr=rate_per_second * 3600,
                        notes="H3 L40S + 8 CPU + 64GiB, hors modèles/stockage"),
            diagnostics=metadata,
        )
        output.add(path, "video", "video/mp4", engine="modal_h3", simulated=False)
        return output


class FrenchEdgeVoice(Engine):
    info = EngineInfo(name="edge_tts_fr", kind="tts", label="Voix française Henri", provider="edge-tts", gpu="CPU", verified=True)

    def available(self):
        if not _env_flag("PVS_MODAL_ENABLED", False):
            return False, "Voix du parcours Modal désactivée"
        try:
            import edge_tts
            return True, ""
        except ImportError:
            return False, "Installer edge-tts sur le serveur"

    def run(self, request, ctx):
        import edge_tts

        text = str(request.params.get("text") or request.shot.get("dialogue") or "").strip()
        if not text:
            raise ValueError("Voix: dialogue vide")
        ctx.check_cancelled()
        ctx.log("Synthèse française Henri", progress=0.1, stage="tts")
        mp3 = request.out("voice_fr.mp3")
        edge_tts.Communicate(text, voice=str(request.params.get('voice') or 'fr-FR-HenriNeural')).save_sync(str(mp3))
        wav = request.out("voice_fr.wav")
        media.run_ffmpeg(["-i", str(mp3), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
        out = EngineOutput()
        out.add(wav, "audio", "audio/wav", engine=self.info.name, simulated=False)
        return out
