#!/usr/bin/env bash
# Install LTX-2.5 native pipelines on a GPU host (Ubuntu 22.04+ / CUDA 12.8+).
# Runtime target: 1x H100 80GB for DFR 1080p, or A100 80GB with fp8-cast + offload.
set -euo pipefail

LTX_DIR="${PVS_LTX_REPO:-/opt/LTX-2}"
MODEL_DIR="${PVS_LTX_MODELS:-/models/ltx-2.5}"
HF_MODEL="${HF_LTX_MODEL:-Lightricks/LTX-2.5}"

command -v nvidia-smi >/dev/null || { echo "Pas de GPU NVIDIA détecté."; exit 1; }
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv

command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh

if [ ! -d "$LTX_DIR" ]; then
  git clone https://github.com/Lightricks/LTX-2.git "$LTX_DIR"
fi
cd "$LTX_DIR"
git pull --ff-only || true
uv sync --extra natten

mkdir -p "$MODEL_DIR"
# ~66 GiB. Keep this on a persistent network volume: re-downloading per pod costs
# more than the GPU time saved.
hf auth login
hf download "$HF_MODEL" \
  diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors \
  text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors \
  vae/ltx-2.5-video-vae-bf16.safetensors \
  vae/ltx-2.5-audio-vae-bf16.safetensors \
  latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors \
  --local-dir "$MODEL_DIR"

hf download Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler \
  ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors \
  --local-dir "$MODEL_DIR/loras"

cat <<EOF
LTX installé.
  PVS_LTX_REPO=$LTX_DIR
  PVS_LTX_MODELS=$MODEL_DIR
Smoke test (30 s, distilled):
  cd $LTX_DIR && uv run python -m ltx_pipelines.distilled \\
    --transformer-path $MODEL_DIR/diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors \\
    --text-encoder-path $MODEL_DIR/text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors \\
    --video-vae-path $MODEL_DIR/vae/ltx-2.5-video-vae-bf16.safetensors \\
    --audio-vae-path $MODEL_DIR/vae/ltx-2.5-audio-vae-bf16.safetensors \\
    --spatial-upsampler-path $MODEL_DIR/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors \\
    --num-frames 121 --seed 42 --output-path /tmp/ltx_smoke.mp4 \\
    --prompt "A medium close-up of a man speaking to camera in a dark studio, cinematic blue rim light"
EOF
