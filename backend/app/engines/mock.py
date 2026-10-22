"""Simulation engine — the pipeline's test double.

This engine draws gradient plates and burns a "SIMULATION" banner. It exists so
that projects, jobs, QC, subtitling and export can be developed and tested
end-to-end without a GPU. It is never model output and every job it produces is
flagged `simulated: true` in the database and in the UI.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .. import graphics, media
from ..cost import Usage
from .base import Engine, EngineInfo, EngineOutput, EngineRequest

SIM_BANNER = "SIMULATION · AUCUN MODÈLE IA"
PALETTES = [
    ("0x0B1220", "0x1E3A8A", "0x38BDF8"),
    ("0x120B1E", "0x3B1E7A", "0xB983F5"),
    ("0x0B1A16", "0x0F5F4F", "0x5EEAD4"),
    ("0x1A0B0B", "0x7A1E1E", "0xF59E0B"),
]


def _filter_path(path: Path) -> str:
    """Escape a filename for use inside an ffmpeg filter option."""
    return str(path).replace("\\", "/").replace(":", "\\:")


def _palette(seed_text: str) -> tuple[str, str, str]:
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    return PALETTES[digest[0] % len(PALETTES)]


def _size(request: EngineRequest) -> tuple[int, int]:
    fmt = request.params.get("format") or request.project.get("format") or "9:16"
    return {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}.get(fmt, (1080, 1920))


def _banner(path: Path, width: int, height: int, duration: float, title: str, subtitle: str = "") -> Path:
    events = [
        graphics.Event(0.0, duration, SIM_BANNER, style="Label"),
    ]
    if title:
        events.append(graphics.Event(0.0, duration, graphics.wrap(title, 26, 3), style="Caption"))
    if subtitle:
        events.append(graphics.Event(0.0, duration, graphics.wrap(subtitle, 34, 3), style="Subtitle"))
    return graphics.build_ass(events, path, width, height)


class MockVideoEngine(Engine):
    info = EngineInfo(
        name="mock",
        kind="video",
        label="Simulation (plaque de test)",
        capabilities=["text_to_video", "image_to_video", "placeholder"],
        requires_gpu=False,
        provider="local",
        gpu="CPU",
        simulated=True,
        verified=True,
        notes="Génère un plan de test déterministe, sans IA. Sert aux tests de pipeline.",
    )

    def run(self, request: EngineRequest, ctx) -> EngineOutput:
        width, height = _size(request)
        duration = max(1.0, min(request.duration_s, 30.0))
        out_path = request.out("mock.mp4")
        c0, c1, accent = _palette(request.prompt or request.shot.get("title") or "mock")
        label = _banner(
            request.out("mock.ass"), width, height, duration,
            request.shot.get("title") or "Plan de test",
        )
        ctx.log("Rendu de la plaque de test", progress=0.2, stage="render")
        source = (
            f"gradients=s={width}x{height}:c0={c0}:c1={c1}:x0=0:y0=0:x1={width}:y1={height}"
            f":speed=0.01:d={duration}:r=30"
        )
        label_arg = _filter_path(label)
        graph = (
            f"[0:v]drawbox=x=0:y=0:w={width}:h={height}:color={accent}@0.10:t=fill,"
            f"subtitles=filename='{label_arg}'[v]"
        )
        media.run_ffmpeg(
            [
                "-f", "lavfi", "-i", source,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-filter_complex", graph,
                "-map", "[v]", "-map", "1:a", "-t", f"{duration}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_path),
            ],
            timeout=600,
            log_path=request.out("ffmpeg.log"),
        )
        out = EngineOutput(
            usage=Usage(provider="local", gpu="CPU", gpu_seconds=0.0, notes="simulation"),
            notes="Plan simulé (aucune génération IA)",
            diagnostics={"simulated": True},
        )
        out.add(out_path, "video", "video/mp4", simulated=True, engine="mock")
        return out


class MockAvatarEngine(Engine):
    info = EngineInfo(
        name="mock_avatar",
        kind="avatar",
        label="Simulation avatar (aucun visage réel)",
        capabilities=["talking_head_placeholder"],
        requires_gpu=False,
        provider="local",
        gpu="CPU",
        simulated=True,
        verified=True,
        notes="Ne produit aucun visage. Sert uniquement à valider le parcours avatar.",
    )

    def run(self, request: EngineRequest, ctx) -> EngineOutput:
        width, height = _size(request)
        duration = max(1.0, min(request.duration_s, 60.0))
        audio_path = request.inputs.get("audio_path")
        c0, c1, accent = _palette("avatar" + (request.prompt or ""))
        label = _banner(
            request.out("avatar.ass"), width, height, duration, "AVATAR SIMULÉ",
        )
        ctx.log("Avatar simulé : plaque + bandeau", progress=0.3, stage="render")
        label_arg = _filter_path(label)
        graph = (
            f"drawbox=x={width // 2 - 260}:y={height // 2 - 520}:w=520:h=1040:color={accent}@0.18:t=fill,"
            f"drawbox=x={width // 2 - 260}:y={height // 2 - 520}:w=520:h=1040:color={accent}@0.7:t=3,"
            f"subtitles=filename='{label_arg}'"
        )
        inputs = [
            "-f", "lavfi", "-i", f"gradients=s={width}x{height}:c0={c0}:c1={c1}:speed=0.01:d={duration}:r=30",
        ]
        if audio_path and Path(str(audio_path)).exists():
            inputs += ["-i", str(audio_path)]
            # keep the planned shot length; pad short voice-overs with silence
            # instead of shortening the timeline
            audio_graph = (
                f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"apad,atrim=duration={duration},asetpts=PTS-STARTPTS[a]"
            )
            graph = f"[0:v]{graph}[v];{audio_graph}"
            audio_map = "[a]"
        else:
            inputs += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
            audio_map = "1:a"
        media.run_ffmpeg(
            [
                *inputs,
                "-filter_complex", graph,
                "-map", "[v]", "-map", audio_map, "-t", f"{duration}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-shortest", str(request.out("mock_avatar.mp4")),
            ],
            timeout=600,
            log_path=request.out("ffmpeg.log"),
        )
        out = EngineOutput(
            usage=Usage(provider="local", gpu="CPU", gpu_seconds=0.0, notes="simulation"),
            notes="Avatar simulé : aucun visage généré",
            diagnostics={"simulated": True},
        )
        out.add(request.out("mock_avatar.mp4"), "video", "video/mp4", simulated=True, engine="mock_avatar")
        return out


class MockImageEngine(Engine):
    info = EngineInfo(
        name="mock_image",
        kind="image",
        label="Simulation image (plaque de test)",
        capabilities=["text_to_image", "placeholder"],
        requires_gpu=False,
        provider="local",
        gpu="CPU",
        simulated=True,
        verified=True,
        notes="Plaque de test pour la gestion des références et des variantes.",
    )

    def run(self, request: EngineRequest, ctx) -> EngineOutput:
        width, height = _size(request)
        c0, c1, accent = _palette("image" + (request.prompt or "ref"))
        out_path = request.out("mock_reference.png")
        label = graphics.build_ass(
            [graphics.Event(0, 5, SIM_BANNER, "Label"),
             graphics.Event(0, 5, graphics.wrap(request.prompt or "référence", 30, 3), "Caption")],
            request.out("mock_image.ass"), width, height,
        )
        media.run_ffmpeg(
            [
                "-f", "lavfi", "-i", f"gradients=s={width}x{height}:c0={c0}:c1={c1}:d=1:r=1",
                "-vf", f"subtitles=filename='{_filter_path(label)}'",
                "-frames:v", "1", str(out_path),
            ],
            timeout=120,
        )
        out = EngineOutput(
            usage=Usage(provider="local", gpu="CPU", gpu_seconds=0.0, notes="simulation"),
            notes="Image simulée",
            diagnostics={"simulated": True},
        )
        out.add(out_path, "image", "image/png", simulated=True, engine="mock_image")
        return out


class MockTTSEngine(Engine):
    info = EngineInfo(
        name="mock_tts",
        kind="tts",
        label="Simulation voix (tonalité, pas de parole)",
        capabilities=["placeholder_audio"],
        requires_gpu=False,
        provider="local",
        gpu="CPU",
        simulated=True,
        verified=True,
        notes="Produit un bip calibré à la durée estimée. Aucune voix, aucun texte prononcé.",
    )

    def run(self, request: EngineRequest, ctx) -> EngineOutput:
        text = str(request.params.get("text") or request.shot.get("dialogue") or "")
        words = max(1, len(text.split()))
        duration = round(max(1.0, words / 2.6), 2)  # ~156 mots/min, débit d'un présentateur
        out_path = request.out("mock_voice.wav")
        media.run_ffmpeg(
            [
                "-f", "lavfi", "-i", f"sine=frequency=180:sample_rate=48000:duration={duration}",
                "-af", "volume=0.06,tremolo=f=5:d=0.7",
                "-c:a", "pcm_s16le", str(out_path),
            ],
            timeout=120,
        )
        out = EngineOutput(
            usage=Usage(provider="local", gpu="CPU", notes="simulation"),
            notes=f"Audio simulé ({duration}s) — aucune parole",
            diagnostics={"simulated": True, "estimated_duration_s": duration},
        )
        out.add(out_path, "audio", "audio/wav", simulated=True, duration_s=duration)
        return out


def build_engines() -> list[Engine]:
    return [MockVideoEngine(), MockAvatarEngine(), MockImageEngine(), MockTTSEngine()]
