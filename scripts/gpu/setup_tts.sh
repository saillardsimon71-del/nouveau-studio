#!/usr/bin/env bash
# French voice stack. CPU is enough for Chatterbox (a few seconds per phrase);
# a T4/4090 makes iteration comfortable and allows VoxCPM2.
set -euo pipefail

VENV="${PVS_TTS_VENV:-/opt/tts-venv}"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q --upgrade pip

# Chatterbox Multilingual (primary)
pip install -q "chatterbox-tts"

# VoxCPM2 (alternative, 48 kHz)
pip install -q "voxcpm" soundfile

python "$(dirname "$0")/tts_chatterbox.py" --check || true
python "$(dirname "$0")/tts_voxcpm.py" --check || true

cat <<EOF
TTS installé dans $VENV
  PVS_TTS_PYTHON=$VENV/bin/python
Test français:
  $VENV/bin/python $(dirname "$0")/tts_chatterbox.py \\
    --text "Et si tu pouvais automatiser toutes ces tâches qui te font perdre du temps ?" \\
    --out /tmp/fr_test.wav --language fr
EOF
