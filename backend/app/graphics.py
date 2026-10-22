"""Text and graphics overlays, rendered through ASS (libass).

Why ASS rather than `drawtext`: a single, well-specified subtitle/text engine
handles subtitles, lower thirds, title cards and end cards with consistent
typography, and every modern ffmpeg build ships libass. It also means the
burned-in text in a preview is exactly the text that ships in the export.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

FONT = "DejaVu Sans"  # present on Linux CI/containers; swap for Montserrat in self-hosted images


def ts(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


@dataclass
class Event:
    start: float
    end: float
    text: str
    style: str = "Subtitle"
    layer: int = 0


@dataclass
class AssStyle:
    name: str
    font: str = FONT
    size: int = 64
    primary: str = "&H00FFFFFF"
    outline_colour: str = "&H00000000"
    back_colour: str = "&H80000000"
    bold: int = 0
    border_style: int = 1
    outline: float = 3.0
    shadow: float = 0.0
    alignment: int = 2
    margin_l: int = 60
    margin_r: int = 60
    margin_v: int = 150
    extra: dict = field(default_factory=dict)


SUBTITLE = AssStyle(name="Subtitle", size=58, alignment=2, margin_v=190, outline=3.2)
TITLE = AssStyle(name="Title", size=96, bold=1, alignment=5, margin_v=40, outline=3.0)
LABEL = AssStyle(name="Label", size=40, alignment=7, margin_l=56, margin_v=56, outline=2.0,
                 primary="&H00D8E4FF")
# captions sit under the top label so they never collide with bottom subtitles
CAPTION = AssStyle(name="Caption", size=40, alignment=8, margin_v=120, primary="&H00C9D6E8")


def _style_line(style: AssStyle) -> str:
    return (
        f"Style: {style.name},{style.font},{style.size},{style.primary},&H000000FF,"
        f"{style.outline_colour},{style.back_colour},{style.bold},0,0,0,100,100,0,0,"
        f"{style.border_style},{style.outline},{style.shadow},{style.alignment},"
        f"{style.margin_l},{style.margin_r},{style.margin_v},1"
    )


def build_ass(
    events: Sequence[Event],
    path: str | Path,
    width: int = 1080,
    height: int = 1920,
    styles: Iterable[AssStyle] = (SUBTITLE, TITLE, LABEL, CAPTION),
) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    head = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    head += [_style_line(s) for s in styles]
    head += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    body = []
    for ev in events:
        text = ev.text.replace("\n", r"\N").replace("{", "(").replace("}", ")")
        if not text.strip():
            continue
        body.append(
            f"Dialogue: {ev.layer},{ts(ev.start)},{ts(ev.end)},{ev.style},,0,0,0,,{text}"
        )
    p.write_text("\n".join(head + body) + "\n", encoding="utf-8")
    return p


def wrap(text: str, max_chars: int = 34, max_lines: int = 3) -> str:
    """Greedy wrap that keeps words whole; subtitle-friendly."""
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])]
    return "\n".join(lines)


def subtitle_events(shots: Sequence[dict], cue_max_chars: int = 34) -> list[Event]:
    """Build subtitle cues from shot dialogue, timed inside each shot window.

    Long lines are split into several cues rather than shown as one wall of text.
    `shots` needs `start_s`, `duration_s` and `dialogue`.
    """
    events: list[Event] = []
    for shot in shots:
        dialogue = (shot.get("dialogue") or "").strip()
        if not dialogue:
            continue
        start = float(shot["start_s"])
        duration = float(shot["duration_s"])
        chunks = _split_cues(dialogue, cue_max_chars)
        total_chars = sum(len(c) for c in chunks) or 1
        cursor = start
        # keep the cue on screen for the whole shot, but never on screen for <0.9s
        usable = max(duration, 0.9)
        for chunk in chunks:
            span = usable * (len(chunk) / total_chars)
            span = max(0.9, span)
            events.append(Event(start=cursor, end=min(start + duration, cursor + span), text=chunk, style="Subtitle"))
            cursor += span
    return events


def subtitle_events_for_srt(segments: Sequence[dict], transition_s: float = 0.0) -> list[Event]:
    """Cue list for a sidecar .srt, using the same timing as the burned-in track."""
    timeline = []
    cursor = 0.0
    for index, seg in enumerate(segments):
        timeline.append(
            {"start_s": cursor, "duration_s": seg["duration_s"], "dialogue": seg.get("dialogue", "")}
        )
        cursor += seg["duration_s"] - (transition_s if index < len(segments) - 1 else 0.0)
    return subtitle_events(timeline)


def _split_cues(text: str, max_chars: int) -> list[str]:
    import re

    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text) if s.strip()]
    cues: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            cues.append(sentence)
            continue
        # split on punctuation first, then on words
        parts = [p.strip() for p in re.split(r"(?<=[,;:—])\s+", sentence) if p.strip()]
        for part in parts:
            if len(part) <= max_chars:
                cues.append(part)
            else:
                cues.extend(wrap(part, max_chars, 2).split("\n"))
    # merge very short trailing cues into the previous one
    merged: list[str] = []
    for cue in cues:
        if merged and len(cue) < 12 and len(merged[-1]) + len(cue) + 1 <= max_chars:
            merged[-1] = f"{merged[-1]} {cue}"
        else:
            merged.append(cue)
    return merged or [" "]
