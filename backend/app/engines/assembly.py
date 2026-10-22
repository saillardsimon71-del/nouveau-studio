"""Final assembly: clips + music + subtitles + grading -> publishable file.

This is deliberately plain ffmpeg. It is fast, deterministic, needs no GPU, and
runs the same on a laptop and on a rented pod. Every parameter that affects the
look (transition, loudness, subtitle style) is explicit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import graphics, media
from ..cost import Usage
from .base import Engine, EngineInfo, EngineOutput, EngineRequest

SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}


def _esc(path: Path | str) -> str:
    # ffmpeg filtergraph escaping for filenames used inside filter options
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


class AssemblyEngine(Engine):
    info = EngineInfo(
        name="ffmpeg_assembly",
        kind="assembly",
        label="Montage ffmpeg (sous-titres, musique, transitions)",
        capabilities=["concat", "subtitles", "music_bed", "loudnorm", "xfade", "poster", "srt"],
        requires_gpu=False,
        provider="local",
        gpu="CPU",
        simulated=False,
        verified=True,
        notes="Montage déterministe, sans IA. Valide réellement dans cet environnement.",
    )

    def run(self, request: EngineRequest, ctx) -> EngineOutput:
        clips: list[dict[str, Any]] = list(request.inputs.get("clips") or [])
        if not clips:
            raise ValueError("assembly needs at least one clip")

        out_spec = request.params.get("format") or request.project.get("format") or "9:16"
        width, height = SIZES.get(out_spec, SIZES["9:16"])
        fps = int(request.params.get("fps") or 30)
        fps = 30 if fps not in (24, 25, 30, 50, 60) else fps
        subtitles = bool(request.params.get("subtitles", True))
        transitions = bool(request.params.get("transitions", True))
        loudness_target = float(request.params.get("loudness_target") or -14.0)
        music_path = request.params.get("music_path") or request.project.get("music_path")
        music_gain = float(request.params.get("music_gain_db", -20.0))
        fade_s = float(request.params.get("transition_s") or 0.35)
        title_card = bool(request.params.get("title_card", False))

        ctx.log(f"Montage de {len(clips)} plan(s) en {width}x{height}@{fps}", progress=0.05, stage="prepare")

        # --- 1. measure and normalise plan durations -------------------------------
        segments: list[dict[str, Any]] = []
        for index, clip in enumerate(clips):
            ctx.check_cancelled()
            path = Path(clip["path"])
            if not path.exists():
                raise FileNotFoundError(f"clip manquant: {path}")
            info = media.probe(path)
            target = float(clip.get("duration_s") or info.duration_s or 1.0)
            # never stretch a clip: if the engine returned a shorter take, the
            # timeline uses the real duration so audio and subtitles stay in sync
            effective = round(min(target, info.duration_s) if info.duration_s else target, 3)
            segments.append(
                {
                    "path": path,
                    "duration_s": max(0.5, effective),
                    "dialogue": clip.get("dialogue", ""),
                    "title": clip.get("title", ""),
                    "kind": clip.get("kind", "b_roll"),
                    "transition": clip.get("transition", "cut"),
                    "has_audio": info.has_audio,
                    "fps": info.fps or fps,
                    "index": index,
                }
            )
        total = round(sum(s["duration_s"] for s in segments) - (fade_s * (len(segments) - 1) if transitions and len(segments) > 1 else 0), 3)

        # --- 2. normalise every segment to identical geometry ---------------------
        # Two-pass: normalise to intermediate files, then assemble. Far more robust
        # than one giant graph (xfade refuses variable frame rates, and a single
        # bad source otherwise kills the whole export).
        work = request.out("normalised")
        work.mkdir(parents=True, exist_ok=True)
        normalised: list[Path] = []
        for i, seg in enumerate(segments):
            ctx.check_cancelled()
            target = work / f"seg_{i:02d}.mp4"
            graph_parts = [
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p,settb=AVTB,"
                f"tpad=stop_mode=clone:stop_duration=1[v]"
            ]
            cmd = ["-i", str(seg["path"])]
            if seg["has_audio"]:
                graph_parts.append("[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a]")
            else:
                cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
                graph_parts.append(f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                                   f"atrim=duration={seg['duration_s']}[a]")
            media.run_ffmpeg(
                [
                    *cmd,
                    "-filter_complex", ";".join(graph_parts),
                    "-map", "[v]", "-map", "[a]",
                    "-t", f"{seg['duration_s']}", "-r", str(fps),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                    str(target),
                ],
                timeout=900,
                log_path=request.out(f"normalise_{i}.log"),
            )
            normalised.append(target)
            seg["normalised"] = str(target)
            ctx.log(f"Plan {i + 1}/{len(segments)} normalisé", progress=0.05 + 0.2 * (i + 1) / len(segments),
                    stage="normalise")

        # --- 3. concatenate (xfade chain when transitions are on) ------------------
        inputs = []
        for path in normalised:
            inputs += ["-i", str(path)]
        filters: list[str] = []
        if len(normalised) == 1:
            v_last, a_last = "0:v", "0:a"
        elif transitions:
            v_prev, a_prev = "0:v", "0:a"
            cumulative = segments[0]["duration_s"]
            for i in range(1, len(segments)):
                offset = round(cumulative - fade_s, 3)
                v_out, a_out = f"vx{i}", f"ax{i}"
                filters.append(f"[{v_prev}][{i}:v]xfade=transition=fade:duration={fade_s}:offset={offset}[{v_out}]")
                filters.append(f"[{a_prev}][{i}:a]acrossfade=d={fade_s}:c1=tri:c2=tri[{a_out}]")
                v_prev, a_prev = v_out, a_out
                cumulative = round(cumulative + segments[i]["duration_s"] - fade_s, 3)
            v_last, a_last = v_prev, a_prev
        else:
            pairs = "".join(f"[{i}:v][{i}:a]" for i in range(len(normalised)))
            filters.append(f"{pairs}concat=n={len(normalised)}:v=1:a=1[vcat][acat]")
            v_last, a_last = "vcat", "acat"

        # --- 4. burned-in text (subtitles, titles) --------------------------------
        events: list[graphics.Event] = []
        if subtitles:
            cursor = 0.0
            timeline = []
            for seg in segments:
                timeline.append({"start_s": cursor, "duration_s": seg["duration_s"], "dialogue": seg["dialogue"]})
                cursor += seg["duration_s"] - (fade_s if transitions and seg["index"] < len(segments) - 1 else 0)
            events += graphics.subtitle_events(timeline)
        if title_card and segments:
            events.append(
                graphics.Event(start=0.15, end=min(2.2, segments[0]["duration_s"]), text=graphics.wrap(
                    request.project.get("name", ""), 22, 2), style="Title")
            )
        # every plan keeps a discreet corner label so a review can identify takes
        label = bool(request.params.get("shot_labels", False))
        if label:
            cursor = 0.0
            for seg in segments:
                events.append(
                    graphics.Event(start=cursor + 0.1, end=cursor + seg["duration_s"] - 0.1,
                                   text=f"PLAN {seg['index'] + 1:02d} · {seg['kind']}", style="Label")
                )
                cursor += seg["duration_s"]

        v_text = v_last
        if events:
            ass_path = request.out("subtitles.ass")
            graphics.build_ass(events, ass_path, width, height)
            filters.append(f"[{v_last}]subtitles=filename='{_esc(ass_path)}'[vsub]")
            v_text = "vsub"

        # --- 5. music bed + loudness ---------------------------------------------
        a_next = a_last
        music_input_index = len(segments)
        has_music = bool(music_path) and Path(str(music_path)).exists()
        if has_music:
            inputs += ["-stream_loop", "-1", "-i", str(music_path)]
            filters.append(
                f"[{music_input_index}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"atrim=duration={total},volume={music_gain}dB,"
                f"afade=t=in:st=0:d=1.2,afade=t=out:st={max(0.0, total - 1.5)}:d=1.5[music]"
            )
            filters.append(
                f"[{a_last}][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[amixed]"
            )
            a_next = "amixed"
        filters.append(
            f"[{a_next}]loudnorm=I={loudness_target}:TP=-1.5:LRA=11,"
            f"atrim=duration={total},asetpts=PTS-STARTPTS[aout]"
        )

        # --- 6. encode -----------------------------------------------------------
        out_path = request.out(f"export_{out_spec.replace(':', 'x')}.mp4")
        graph = ";".join(filters)
        graph_path = request.out("filtergraph.txt")
        graph_path.write_text(graph.replace(";", ";\n"), encoding="utf-8")
        # a bare input spec ("0:v") is mapped as-is; a filter output needs brackets.
        # Audio always ends on the loudnorm output label.
        map_v = v_text if ":" in v_text else f"[{v_text}]"
        ctx.log("Encodage H.264 + AAC", progress=0.35, stage="encode")
        media.run_ffmpeg(
            [
                *inputs,
                "-filter_complex", graph,
                "-map", map_v,
                "-map", "[aout]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-t", f"{total}",
                "-movflags", "+faststart",
                str(out_path),
            ],
            timeout=3600,
            log_path=request.out("ffmpeg.log"),
        )

        ctx.log("Génération de la miniature et du SRT", progress=0.9, stage="finish")
        poster = request.out("poster.jpg")
        try:
            media.run_ffmpeg(["-ss", "1.0", "-i", str(out_path), "-frames:v", "1", "-q:v", "3", str(poster)])
        except media.MediaError:
            poster = None  # type: ignore[assignment]

        srt_path = request.out("subtitles.srt")
        if subtitles:
            srt_path.write_text(_srt(graphics.subtitle_events_for_srt(segments, fade_s if transitions else 0.0)), encoding="utf-8")

        out = EngineOutput(
            usage=Usage(provider="local", gpu="CPU", gpu_seconds=0.0, notes="montage CPU"),
            notes=f"{len(segments)} plans, {total}s, {width}x{height}@{fps}",
            diagnostics={"duration_s": total, "segments": len(segments), "music": bool(has_music)},
        )
        out.add(out_path, "export", "video/mp4", duration_s=total, size=f"{width}x{height}")
        if poster:
            out.add(Path(poster), "poster", "image/jpeg")
        if subtitles and srt_path.exists():
            out.add(srt_path, "subtitles", "text/plain")
        out.add(graph_path, "debug", "text/plain")
        return out


def _srt(events: list[graphics.Event]) -> str:
    def stamp(t: float) -> str:
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, ev in enumerate(events, start=1):
        lines.append(f"{i}\n{stamp(ev.start)} --> {stamp(ev.end)}\n{ev.text}\n")
    return "\n".join(lines)


def splice_region(original: str | Path, replacement: str | Path, start_s: float, end_s: float, out_path: str | Path) -> Path:
    """Put a regenerated region back into its clip.

    Used by targeted regeneration: LTX Retake returns only the corrected window,
    so the studio rebuilds the full clip around it. Re-encodes once; not applied
    to the original file, which stays untouched as provenance.
    """
    src = Path(original)
    repl = Path(replacement)
    out = Path(out_path)
    info = media.probe(src)
    total = info.duration_s
    start_s = max(0.0, min(start_s, total))
    end_s = max(start_s + 0.1, min(end_s, total))
    tail = max(0.0, total - end_s)
    repl_info = media.probe(repl)

    filters = [
        "[0:v]split=2[ov1][ov2]",
        f"[ov1]trim=0:{start_s:.3f},setpts=PTS-STARTPTS[v1]",
        f"[ov2]trim=start={end_s:.3f},setpts=PTS-STARTPTS[v3]",
        "[1:v]setpts=PTS-STARTPTS[v2]",
    ]
    if info.has_audio:
        filters += [
            "[0:a]asplit=2[oa1][oa2]",
            f"[oa1]atrim=0:{start_s:.3f},asetpts=PTS-STARTPTS[a1]",
            f"[oa2]atrim=start={end_s:.3f},asetpts=PTS-STARTPTS[a3]",
        ]
    else:
        filters += [
            f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={start_s:.3f},asetpts=PTS-STARTPTS[a1]",
            f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={tail:.3f},asetpts=PTS-STARTPTS[a3]",
        ]
    if repl_info.has_audio:
        filters.append("[1:a]asetpts=PTS-STARTPTS[a2]")
    else:
        filters.append(
            f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={end_s - start_s:.3f},asetpts=PTS-STARTPTS[a2]"
        )
    filters.append("[v1][a1][v2][a2][v3][a3]concat=n=3:v=1:a=1[vout][aout]")
    media.run_ffmpeg(
        [
            "-i", str(src), "-i", str(repl),
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
        ],
        timeout=1800,
    )
    return out
