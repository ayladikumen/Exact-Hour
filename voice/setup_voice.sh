#!/usr/bin/env bash
# =============================================================================
#  Exact Hour - voice setup (run ON THE PI)
# -----------------------------------------------------------------------------
#  Installs the speech-to-text deps and downloads the small offline Vosk model
#  into voice/models/. Run once from the repo root:   bash voice/setup_voice.sh
# =============================================================================
set -e

# 0) Make sure we're inside the project's virtual environment (same one the
#    clock uses) so vosk/sounddevice land where main.py can import them.
if [ -z "$VIRTUAL_ENV" ]; then
  echo "WARNING: no virtual environment is active."
  echo "  Activate it first:   source venv/bin/activate"
  echo "  (otherwise vosk/sounddevice may install where main.py can't see them)"
  echo
fi

# 1) System audio libs Vosk/sounddevice need (PortAudio).
sudo apt-get update
sudo apt-get install -y python3-pip portaudio19-dev libportaudio2 unzip wget

# 2) Python packages (into the active venv).
pip install vosk sounddevice

# 3) Small English model (~50 MB) - fits the Pi Zero 2 W.
MODEL_DIR="voice/models"
MODEL_NAME="vosk-model-small-en-us-0.15"
mkdir -p "$MODEL_DIR"
if [ ! -d "$MODEL_DIR/$MODEL_NAME" ]; then
  echo "Downloading $MODEL_NAME ..."
  wget -O "$MODEL_DIR/$MODEL_NAME.zip" \
    "https://alphacephei.com/vosk/models/$MODEL_NAME.zip"
  unzip -q "$MODEL_DIR/$MODEL_NAME.zip" -d "$MODEL_DIR"
  rm "$MODEL_DIR/$MODEL_NAME.zip"
fi

echo
echo "Done. Model at $MODEL_DIR/$MODEL_NAME"
echo "Set ENABLE_VOICE=True and BRAIN_URL in main.py, then run: python3 main.py"
echo "(Other languages: pick a model at https://alphacephei.com/vosk/models)"
