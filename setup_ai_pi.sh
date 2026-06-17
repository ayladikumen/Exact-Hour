#!/usr/bin/env bash
# =============================================================================
#  Exact Hour - set up the local-AI fallback on a Raspberry Pi Zero 2 W
# -----------------------------------------------------------------------------
#  Run this ON THE PI (not your PC), from inside the project folder, ideally
#  with your virtual environment active (see basic_installation.md section 6):
#
#      source venv/bin/activate
#      bash setup_ai_pi.sh
#
#  It is safe to re-run. The model file itself ships with the repo
#  (models/SmolLM2-135M-Instruct-Q4_0.gguf), so this script only sets up swap
#  and the llama.cpp Python bindings.
# =============================================================================
set -e

echo ">>> 1/3  Configuring 1 GB swap (512 MB RAM is tight - this prevents OOM kills)..."
sudo dphys-swapfile swapoff || true
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
echo "    Swap is now:"
free -h | awk '/Swap/ {print "    " $0}'

echo ">>> 2/3  Installing build tools + llama-cpp-python (compiles for ARM - be patient)..."
sudo apt-get update
sudo apt-get install -y build-essential cmake python3-pip python3-dev
pip install --upgrade pip
pip install llama-cpp-python

echo ">>> 3/3  Checking the model file..."
if [ -f "models/SmolLM2-135M-Instruct-Q4_0.gguf" ]; then
  echo "    Model found (committed with the repo)."
else
  echo "    WARNING: models/SmolLM2-135M-Instruct-Q4_0.gguf is missing."
  echo "    It should have come with the repo. Re-clone, or download it from:"
  echo "    https://huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF"
fi

echo ""
echo ">>> Done. Test the local AI with:"
echo "        python assistant.py --llm"
echo "    (Without --llm it still works using the fast rule-based parser.)"
