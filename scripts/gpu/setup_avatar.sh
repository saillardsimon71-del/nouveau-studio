#!/usr/bin/env bash
# Talking-head stack: LongCat-Video-Avatar 1.5 (primary), InfiniteTalk (fallback).
set -euo pipefail

AVATAR_DIR="${PVS_AVATAR_REPO:-/opt/LongCat-Video}"
WEIGHTS="${PVS_AVATAR_WEIGHTS:-/models/LongCat-Video-Avatar-1.5}"

command -v nvidia-smi >/dev/null || { echo "Pas de GPU NVIDIA détecté."; exit 1; }

if [ ! -d "$AVATAR_DIR" ]; then
  git clone https://github.com/meituan-longcat/LongCat-Video.git "$AVATAR_DIR"
fi
cd "$AVATAR_DIR"
git pull --ff-only || true
pip install -r requirements.txt -r requirements_avatar.txt

mkdir -p "$WEIGHTS"
hf auth login
hf download meituan-longcat/LongCat-Video-Avatar-1.5 --local-dir "$WEIGHTS"

cat <<EOF
Avatar installé.
  PVS_AVATAR_REPO=$AVATAR_DIR
  PVS_AVATAR_WEIGHTS=$WEIGHTS
Le studio écrit un input JSON (prompt / cond_image / cond_audio.person1) puis appelle :
  torchrun --nproc_per_node=<N> run_demo_avatar_single_audio_to_video.py \\
    --context_parallel_size=<N> --checkpoint_dir=$WEIGHTS --stage_1=ai2v \\
    --input_json=<job>/avatar_input.json --model_type avatar-v1.5 --use_distill --use_int8 \\
    --resolution 720

Fallback (InfiniteTalk, unlimited length / video-to-video dubbing):
  git clone https://github.com/MeiGen-AI/InfiniteTalk.git /opt/InfiniteTalk
EOF
