import math
import json
import subprocess
from pathlib import Path


def plan_audio(duration_s, max_segments=1):
    if max_segments not in (1, 2):
        raise ValueError('LongCat accepte un ou deux segments dans ce pilote')
    limit = 3.72 if max_segments == 1 else 6.92
    if not math.isfinite(duration_s) or not 0 < duration_s <= limit + 1e-8:
        raise ValueError(f'LongCat: voix hors limite de {limit}s, aucune accélération autorisée')
    segments = 1 if duration_s <= 3.72 + 1e-8 else 2
    return {'num_segments': segments, 'generation_frames': 93 + (segments - 1) * 80,
            'output_frames': math.ceil(duration_s * 25 - 1e-8), 'source_duration_s': duration_s,
            'fps': 25, 'context_frames': 13}


def select_output(folder, segments):
    stem = 'ai2v_demo_1' if segments == 1 else 'video_continue_2'
    matches = list(Path(folder).rglob(stem + '.mp4'))
    if len(matches) != 1:
        raise ValueError(f'LongCat: sortie de continuation attendue absente ou ambiguë ({stem})')
    return matches[0]


def diagnostic_inputs(image, audio, voice_report, max_segments):
    from .voice import require_validated_voice
    report = json.loads(Path(voice_report).read_text(encoding='utf-8'))
    report = require_validated_voice(audio, report['expected_text'], report)
    plan = plan_audio(report['duration_s'], max_segments)
    photo = Path(image).read_bytes()
    if not photo.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('LongCat: référence PNG requise avant appel distant')
    return photo, Path(audio).read_bytes(), plan


def finish_avatar(raw, source_audio, final, plan):
    duration = plan['output_frames'] / 25
    subprocess.run([
        'ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-i', str(source_audio),
        '-map', '0:v:0', '-map', '1:a:0', '-vf', 'crop=ih*9/16:ih,scale=720:1280',
        '-frames:v', str(plan['output_frames']), '-t', str(duration),
        '-af', f'apad=whole_dur={duration}', '-c:v', 'libx264', '-crf', '19', '-preset', 'fast',
        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(final),
    ], check=True, timeout=240)
