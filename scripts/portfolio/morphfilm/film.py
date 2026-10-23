"""Film assembly: timeline, morph transitions, render loop, encode, QC.

A `Film` is a list of `Shot`s separated by `Transition`s. The render loop walks
the timeline frame by frame, renders the active shot (or the active morph),
applies the *single* shared grade and grain pass, and streams raw frames into
ffmpeg. Nothing is buffered in memory beyond one frame, so a 30 s 1080x1920 film
renders comfortably on two CPU cores.

Two encodes are produced from the same loop: a branded cut (discreet end card)
and a clean cut without any graphic layer, for stock/prospect use.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import atmos, camera, imageops, morph

W, H = 1080, 1920


# --------------------------------------------------------------------------- data


@dataclass
class Shot:
    name: str
    plate: camera.Plate
    duration: float
    cam: Callable[[float], camera.Cam]
    post: Callable[[np.ndarray, float], np.ndarray] | None = None
    sweep: bool = True
    note: str = ""


def plate(path, width, height, overscan=1.24, depth=False):
    """Convenience constructor keeping the overscan choice next to the shot."""
    return camera.Plate(path, width, height, overscan=overscan, depth=depth)


@dataclass
class Transition:
    name: str
    kind: str
    duration: float
    params: dict = field(default_factory=dict)
    drift: float = 0.05          # shared push applied to the morph result
    drift_dir: tuple[float, float] = (0.0, 0.0)


@dataclass
class Film:
    slug: str
    title: str
    shots: list[Shot]
    transitions: list[Transition]
    fps: int
    grade: imageops.Grade
    endcard: dict
    meta: dict = field(default_factory=dict)

    def schedule(self) -> list[tuple[float, float, int]]:
        """(start, end, index) for each shot, accounting for overlap."""
        starts = [0.0]
        for i, tr in enumerate(self.transitions):
            starts.append(starts[-1] + self.shots[i].duration - tr.duration)
        return [(starts[i], starts[i] + s.duration, i) for i, s in enumerate(self.shots)]

    @property
    def duration(self) -> float:
        sched = self.schedule()
        return sched[-1][1]

    @property
    def frames(self) -> int:
        return int(round(self.duration * self.fps))


# --------------------------------------------------------------------------- render


def _mmss(t: float) -> str:
    return f"{int(t // 60):01d}:{t % 60:04.1f}"


def _ease_io(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class Renderer:
    def __init__(self, film: Film, out_dir: Path, log=print):
        self.film = film
        self.out = out_dir
        self.log = log
        self.sched = film.schedule()
        self.grain = imageops.GrainBank()
        self.plans: dict[int, morph.MorphPlan] = {}
        self.endcard_img = None

    # -- plates ------------------------------------------------------------
    def shot_frame(self, index: int, u: float, handheld: bool = False) -> np.ndarray:
        """Render shot `index` at progress `u`.

        `handheld` adds a slow breath to the framing (a real operator is never
        perfectly locked off). The envelope is sin(pi*u), so the first and last
        frames are untouched and a morph always starts and ends on the exact
        same image as the shot.
        """
        shot = self.film.shots[index]
        u = min(1.0, max(0.0, u))
        cam = shot.cam(u)
        if handheld:
            env = math.sin(math.pi * u) ** 1.2
            cam = camera.Cam(
                zoom=cam.zoom * (1.0 + 0.006 * env * math.sin(u * 7.3 + index)),
                pan_x=cam.pan_x + 0.0045 * env * math.sin(u * 5.1 + index * 1.7),
                pan_y=cam.pan_y + 0.0030 * env * math.cos(u * 4.3 + index * 2.3),
                roll_deg=cam.roll_deg + 0.22 * env * math.sin(u * 3.7 + index),
                parallax=cam.parallax, focus_shift=cam.focus_shift)
        img = shot.plate.render(cam)
        if shot.post is not None:
            img = shot.post(img, u)
        return img

    def transition_plan(self, index: int) -> morph.MorphPlan:
        if index in self.plans:
            return self.plans[index]
        tr = self.film.transitions[index]
        a = self.shot_frame(index, 1.0)
        b = self.shot_frame(index + 1, 0.0)
        plan = morph.build_plan(tr.kind, a, b, **tr.params)
        self.plans[index] = plan
        return plan

    # -- frame -------------------------------------------------------------
    def frame(self, t: float) -> tuple[np.ndarray, dict]:
        """Resolve the timeline: a transition window wins over the shots it joins."""
        info: dict = {"t": t}
        for i, tr in enumerate(self.film.transitions):
            t_start = self.sched[i + 1][0]
            if t_start <= t < t_start + tr.duration:
                w = (t - t_start) / tr.duration
                we = _ease_io(w)
                plan = self.transition_plan(i)
                a = self.shot_frame(i, 1.0)
                b = self.shot_frame(i + 1, 0.0)
                img = morph.render_morph(plan, a, b, we)
                env = math.sin(math.pi * min(1.0, max(0.0, w))) ** 0.8
                img = self._drift(img, tr, env)
                img = self._morph_light(img, tr, w, we)
                info.update({"transition": tr.name, "w": round(w, 3)})
                return img, info
        for i, (start, end, idx) in enumerate(self.sched):
            if start <= t <= end or (i == len(self.sched) - 1 and t > end):
                u = min(1.0, max(0.0, (t - start) / max(1e-6, end - start)))
                info.update({"shot": self.film.shots[idx].name, "u": round(u, 3)})
                img = self.shot_frame(idx, u, handheld=True)
                return self._shot_light(img, idx, u), info
        raise RuntimeError(f"timeline gap at t={t}")

    def _drift(self, img: np.ndarray, tr: Transition, env: float) -> np.ndarray:
        z = 1.0 + tr.drift * env
        dx = tr.drift_dir[0] * env * W
        dy = tr.drift_dir[1] * env * H
        m = np.array([[z, 0, (1 - z) * W / 2 - dx], [0, z, (1 - z) * H / 2 - dy]], dtype=np.float32)
        return cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    def _morph_light(self, img: np.ndarray, tr: Transition, w: float, we: float) -> np.ndarray:
        kind = tr.params.get("light", "sweep")
        if kind == "sweep":
            img = atmos.specular_sweep(img, w, angle_deg=22.0, speed=1.1, strength=0.10)
        elif kind == "flare":
            c = tr.params.get("flare_center", (W * 0.5, H * 0.45))
            img = imageops.add_light(img, atmos.flare(c, 0.10 * math.sin(math.pi * w) ** 2))
        img = imageops.add_light(img, atmos.flare((W * 0.5, H * 0.5),
                                                0.012 * math.sin(math.pi * w) ** 3))
        return img

    def _shot_light(self, img: np.ndarray, index: int, u: float) -> np.ndarray:
        shot = self.film.shots[index]
        if shot.sweep:
            img = atmos.specular_sweep(img, u * 1.05, angle_deg=20.0, speed=1.0, strength=0.085)
        return img

    # -- end card ----------------------------------------------------------
    def build_endcard(self, font_dir: Path, title: str, kicker: str, line: str, note: str) -> np.ndarray:
        """Brand end card on transparent RGBA: composited over the moving image."""
        f_light = load_font(font_dir, 44, weight=500)
        f_bold = load_font(font_dir, 96, weight=800)
        f_kick = load_font(font_dir, 30, weight=600)
        f_note = load_font(font_dir, 24, weight=500)
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        mark = 96
        x0, y0 = W // 2 - mark // 2, int(H * 0.345)
        d.rounded_rectangle((x0, y0, x0 + mark, y0 + mark), 26, outline=(220, 165, 105, 255), width=5)
        d.line([(x0 + 24, y0 + 72), (x0 + 24, y0 + 32), (x0 + 66, y0 + 32)], fill=(245, 240, 230, 255), width=5)
        d.line([(x0 + 38, y0 + 62), (x0 + 70, y0 + 28)], fill=(220, 165, 105, 255), width=7)
        d.line([(x0 + 54, y0 + 28), (x0 + 72, y0 + 28), (x0 + 72, y0 + 47)], fill=(220, 165, 105, 255), width=6)
        text = "SiteQuiVend"
        tw = d.textlength(text, font=f_bold)
        d.text(((W - tw) / 2, y0 + mark + 62), text, font=f_bold, fill=(246, 242, 234, 255))
        kick = kicker.upper()
        kw = d.textlength(kick, font=f_kick)
        d.text(((W - kw) / 2, y0 + mark + 190), kick, font=f_kick, fill=(220, 165, 105, 255))
        lw = d.textlength(line, font=f_light)
        d.text(((W - lw) / 2, y0 + mark + 262), line, font=f_light, fill=(232, 228, 220, 255))
        d.line([(W / 2 - 60, y0 + mark + 232), (W / 2 + 60, y0 + mark + 232)], fill=(220, 165, 105, 110), width=2)
        nw = d.textlength(note, font=f_note)
        d.text(((W - nw) / 2, int(H * 0.855)), note, font=f_note, fill=(210, 206, 198, 150))
        return im

    def render(self, out_main: Path, out_clean: Path, font_dir: Path, endcard: dict,
               progress_every: float = 3.0) -> dict:
        film = self.film
        total = film.frames
        endcard_img = self.build_endcard(font_dir, endcard.get("title", self.film.title),
                                         endcard["kicker"], endcard["line"], endcard["note"])
        endcard_arr = np.asarray(endcard_img, dtype=np.float32) / 255.0
        alpha = endcard_arr[..., 3:4]
        rgb = endcard_arr[..., :3]
        endcard_start = max(0.0, film.duration - endcard["duration"])

        cmd = lambda path: [
            ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(film.fps),
            "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-g", str(film.fps * 2),
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            str(path)]

        p_main = subprocess.Popen(cmd(out_main), stdin=subprocess.PIPE)
        p_clean = subprocess.Popen(cmd(out_clean), stdin=subprocess.PIPE)
        started = time.time()
        last = 0.0
        for i in range(total):
            t = i / film.fps
            img, info = self.frame(t)
            graded = imageops.apply_grade(img, film.grade, self.grain, grain_index=i)
            clean = (np.clip(graded, 0, 1) * 255).astype(np.uint8)
            p_clean.stdin.write(clean.tobytes())
            if t >= endcard_start:
                fade = min(1.0, (t - endcard_start) / 0.55)
                rise = int((1.0 - _ease_io(fade)) * 26)
                card = np.roll(rgb, rise, axis=0)
                a = alpha * fade
                # focus-out backdrop: the image keeps moving but softens and
                # darkens, which is both premium and gives the type contrast
                k = min(1.0, (t - endcard_start) / 0.9)
                base = graded
                if k > 0.01:
                    small = cv2.resize(base, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
                    small = cv2.GaussianBlur(small, (0, 0), 5.5 * k)
                    base = base * (1 - k) + cv2.resize(small, (W, H)) * k
                    base = base * (1.0 - 0.55 * k)
                glow = np.exp(-(((np.arange(W)[None, :] - W / 2) ** 2 +
                                 (np.arange(H)[:, None] - H * 0.44) ** 2) / (2 * 520.0 ** 2)))
                base = imageops.add_light(base, glow[..., None] *
                                          np.array([1.0, 0.66, 0.34]) * (0.05 * k))
                composed = base * (1 - a) + card * a
                main = (np.clip(composed, 0, 1) * 255).astype(np.uint8)
            else:
                main = clean
            p_main.stdin.write(main.tobytes())
            if time.time() - last > progress_every or i == total - 1:
                last = time.time()
                pct = 100.0 * (i + 1) / total
                self.log(f"  {pct:5.1f}%  frame {i + 1}/{total}  t={_mmss(t)}  {info}")
        for p in (p_main, p_clean):
            p.stdin.close()
        for p in (p_main, p_clean):
            if p.wait() != 0:
                raise RuntimeError("ffmpeg encode failed")
        return {"frames": total, "render_seconds": round(time.time() - started, 1)}


# --------------------------------------------------------------------------- helpers


def ffmpeg_bin() -> str:
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("ffmpeg introuvable") from exc


def load_font(font_dir: Path, size: int, weight: int = 500):
    candidates = [font_dir / "Manrope.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
    for path in candidates:
        if path.is_file():
            font = ImageFont.truetype(str(path), size)
            try:
                font.set_variation_by_axes([weight])
            except Exception:
                pass
            return font
    return ImageFont.load_default()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
    from app import media
    return media.probe(path).to_dict()


def measure_loudness(path: Path) -> dict:
    """ffmpeg loudnorm first pass, parsed from stderr (no extra dependency)."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(path), "-af",
           "loudnorm=I=-14:TP=-1.3:LRA=9:print_format=json", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True).stderr
    start = out.rfind("{")
    end = out.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError("loudnorm: sortie illisible")
    return json.loads(out[start:end + 1])


def mux(video_in: Path, audio_in: Path, output: Path, title: str, comment: str) -> dict:
    m = measure_loudness(audio_in)
    af = (f"loudnorm=I=-14:TP=-1.3:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
          f"offset={m['target_offset']}:linear=true,aresample=48000")
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_in),
           "-i", str(audio_in), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
           "-af", af, "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2",
           "-shortest", "-movflags", "+faststart", "-metadata", f"title={title}",
           "-metadata", f"comment={comment}", str(output)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1500:])
    return {"video": str(output), "audio_filter": af}


def qc_report(path: Path, fps: int, duration: float) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
    from app import qc
    return qc.inspect_export(path, {"format": "9:16", "fps": fps}, expected_duration_s=duration)


def cover(frame: np.ndarray, path: Path, kicker: str, lines: list[tuple[str, int]],
          font_dir: Path, logo: bool = True) -> None:
    """Vertical cover: the hero frame, a cinematic scrim and two lines of type."""
    im = Image.fromarray((np.clip(frame, 0, 1) * 255).astype(np.uint8)).convert("RGB")
    overlay = Image.new("L", (W, H), 0)
    od = ImageDraw.Draw(overlay)
    top = int(H * 0.42)
    for y in range(top):
        value = 165.0 * max(0.0, 1.0 - y / float(top)) ** 1.5
        od.line([(0, y), (W, y)], fill=int(value))
    bottom_start = int(H * 0.72)
    for y in range(bottom_start, H):
        value = 150.0 * max(0.0, (y - H * 0.72) / (H * 0.28)) ** 1.6
        od.line([(0, y), (W, y)], fill=int(value))
    dark = Image.new("RGB", (W, H), (8, 9, 11))
    im = Image.composite(dark, im, overlay.point(lambda v: v))
    d = ImageDraw.Draw(im)
    d.text((84, 92), kicker.upper(), font=load_font(font_dir, 30, weight=700),
           fill=(222, 172, 112))
    y = 152
    for text, size in lines:
        d.text((84, y), text, font=load_font(font_dir, size, weight=800), fill=(246, 242, 234))
        y += int(size * 1.12)
    if logo:
        d.text((84, H - 152), "SiteQuiVend", font=load_font(font_dir, 36, weight=800),
               fill=(246, 242, 234))
        d.line([(84, H - 100), (320, H - 100)], fill=(222, 172, 112), width=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=95, subsampling=0)
