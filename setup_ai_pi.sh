#!/usr/bin/env bash
# =============================================================================
#  Exact Hour - set up the local-AI fallback on a Raspberry Pi Zero 2 W
# -----------------------------------------------------------------------------
#  Run this ON THE PI (not your PC), from inside the project folder, WITH YOUR
#  VIRTUAL ENVIRONMENT ACTIVE, and WITHOUT sudo:
#
#      cd ~/Exact-Hour
#      source venv/bin/activate          # your prompt should start with (venv)
#      bash setup_ai_pi.sh               # <-- NO sudo here!
#
#  Why no sudo? sudo throws away your virtual environment, so pip would try to
#  install into the locked system Python and fail with "externally-managed-
#  environment". This script calls sudo ONLY for the apt/swap steps that need it.
#
#  It is safe to re-run. The model file ships with the repo
#  (models/SmolLM2-135M-Instruct-Q4_0.gguf). This script sets up everything an
#  end user needs:
#    - 1 GB swap (memory safety on the 512 MB Pi)
#    - LED display + button libraries (luma.led_matrix, gpiozero, lgpio)
#    - the local AI engine (llama-cpp-python)
#  After it finishes:  python assistant.py --llm --display
#
#  >>> Troubleshooting is at the BOTTOM of this file. <<<
# =============================================================================

# --- Guard 1: don't let the whole script run under sudo (kills the venv) ------
if [ "$(id -u)" -eq 0 ]; then
  echo "ERROR: don't run this with sudo. Run it as your normal user:"
  echo "    source venv/bin/activate && bash setup_ai_pi.sh"
  echo "(The script uses sudo internally only where it's actually needed.)"
  exit 1
fi

# --- Guard 2: warn if no virtual environment is active ------------------------
if [ -z "$VIRTUAL_ENV" ]; then
  echo "WARNING: no virtual environment detected (your prompt has no '(venv)')."
  echo "         llama-cpp-python should go in a venv. Activate it first:"
  echo "             source venv/bin/activate"
  echo "         Continuing in 5s anyway... (Ctrl-C to stop)"
  sleep 5
fi

# -----------------------------------------------------------------------------
echo ">>> 1/3  Configuring 1 GB swap (512 MB RAM is tight - this prevents OOM kills)..."
# This step is a safety margin, so never let it abort the rest of the script.
setup_swap() {
  if command -v dphys-swapfile >/dev/null 2>&1; then
    # Classic Raspberry Pi OS path.
    sudo dphys-swapfile swapoff || true
    sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
  else
    # Newer Raspberry Pi OS (Bookworm) has no dphys-swapfile: make a plain swapfile.
    if [ ! -f /swapfile ]; then
      sudo fallocate -l 1G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
      sudo chmod 600 /swapfile
      sudo mkswap /swapfile
    fi
    sudo swapon /swapfile 2>/dev/null || true
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi
}
if setup_swap; then
  echo "    Swap is now:"
  free -h | awk '/Swap/ {print "    " $0}'
else
  echo "    (Swap setup had a problem - continuing anyway; it's only a safety net.)"
fi

# -----------------------------------------------------------------------------
echo ">>> 2/4  Installing build tools..."
sudo apt-get update
sudo apt-get install -y build-essential cmake python3-pip python3-dev python3-venv

# Build/unpack temp goes to a real disk dir, NOT /tmp (which is a small RAM tmpfs
# on the Pi and overflows with "No space left on device"). Single-threaded build
# keeps RAM pressure low on the Pi Zero.
mkdir -p "$HOME/tmp"
export TMPDIR="$HOME/tmp"
export CMAKE_BUILD_PARALLEL_LEVEL=1
pip install --upgrade pip || true

# Helper: pip install into the active venv, retrying with --break-system-packages.
pip_get() {
  if ! pip install --no-cache-dir "$@"; then
    echo "    Plain pip install failed - retrying with --break-system-packages..."
    pip install --no-cache-dir --break-system-packages "$@"
  fi
}

# -----------------------------------------------------------------------------
echo ">>> 3/4  Installing Python libraries..."
echo "    (a) LED display + buttons (luma / gpiozero / lgpio) - needed for --display"
pip_get luma.led_matrix gpiozero lgpio
echo "    (b) Local AI model engine (llama-cpp-python) - compiles for ARM, be patient"
pip_get llama-cpp-python

# -----------------------------------------------------------------------------
echo ">>> 4/4  Checking the model file..."
if [ -f "models/SmolLM2-135M-Instruct-Q4_0.gguf" ]; then
  echo "    Model found (committed with the repo)."
else
  echo "    WARNING: models/SmolLM2-135M-Instruct-Q4_0.gguf is missing."
  echo "    It should have come with the repo. Re-clone, or download it from:"
  echo "    https://huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF"
fi

echo ""
echo ">>> Done! Everything is installed. Run the assistant with:"
echo "        python assistant.py --llm --display"
echo "    --display = show the timer on the LED matrix"
echo "    --llm     = enable the local AI for flexible phrasing"
echo "    (You can drop either flag. With neither, it's text-only + rule-based.)"
echo ""
echo "    NOTE: stop the button timer first so the display is free:"
echo "        sudo systemctl stop exacthour.service"

# =============================================================================
#  TROUBLESHOOTING  (read this if the script fails)
# -----------------------------------------------------------------------------
#  1) "error: externally-managed-environment"
#       Cause:  pip tried to install into the locked SYSTEM Python. This happens
#               if you ran the script with `sudo` (sudo discards your venv), or
#               if no venv was active.
#       Fix:    Run WITHOUT sudo and WITH the venv active:
#                   cd ~/Exact-Hour
#                   source venv/bin/activate     # prompt shows (venv)
#                   bash setup_ai_pi.sh
#               (No venv yet? Make one:  python3 -m venv venv  then activate it.)
#
#  2) "dphys-swapfile: command not found" / "can't read /etc/dphys-swapfile"
#       Cause:  Newer Raspberry Pi OS (Bookworm) doesn't ship dphys-swapfile.
#       Fix:    This script now auto-creates a plain /swapfile instead - just
#               re-run it. (Manual: sudo fallocate -l 1G /swapfile &&
#               sudo chmod 600 /swapfile && sudo mkswap /swapfile &&
#               sudo swapon /swapfile)
#
#  3) "pip: command not found"
#       Fix:    sudo apt install -y python3-pip   (then re-run the script)
#
#  4) "ERROR: ... OSError: [Errno 28] No space left on device"
#       Cause:  /tmp on the Pi is a small RAM-backed tmpfs; the build overflows it
#               even when your SD card has tons of free space (check: df -h /).
#       Fix:    This script now points the build at ~/tmp on the real disk. To do
#               it manually:
#                   mkdir -p ~/tmp
#                   TMPDIR=~/tmp pip install --no-cache-dir llama-cpp-python
#
#  5) llama-cpp-python build is extremely slow or gets killed
#       Cause:  Compiling on a Pi Zero 2 W is slow and RAM-tight.
#       Fix:    Make sure swap is on (step 1 above). The build can take 15-30
#               min - let it finish. If it's "Killed", add more swap (2G) and retry.
#
#  6) "python assistant.py --llm" says "Local AI unavailable"
#       Meaning: llama-cpp-python or the model file isn't found. The assistant
#               still works on rule-based parsing. Re-run this script to finish
#               the install; confirm the model exists under models/.
#
#  7) "Could not start LED display (No module named 'luma')"
#       Cause:  The display libraries aren't in your venv (the systemd service
#               uses the SYSTEM python, which has them; your venv may not).
#       Fix:    This script now installs them. Manually, with the venv active:
#                   pip install luma.led_matrix gpiozero lgpio
#
#  8) "Could not start LED display" with a SPI / device-busy error
#       Cause:  Another program is using the matrix (main.py or the service).
#       Fix:    Stop them first:
#                   sudo systemctl stop exacthour.service
#                   # and Ctrl-C any running `python main.py`
# =============================================================================
