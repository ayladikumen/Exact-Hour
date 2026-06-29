# Exact Hour - Voice (Pi side)

Microphone + **offline speech-to-text** on the Raspberry Pi. It does **not**
run any AI: it captures one spoken command, transcribes it with Vosk, and POSTs
the text to the PC brain (`../pc_brain/`), which does the understanding + action.

## Trigger: double-press the START button

The middle **start/stop button** keeps its normal job — a **single press**
still does start / pause / resume / reset. A **double press** (two quick taps,
in any timer state) means **"talk to the AI"**: the Pi records one command and
sends it to the brain. No new buttons, no enclosure change.

The only cost is that, while voice is enabled, a single press is held back by
`DOUBLE_PRESS_WINDOW` (~0.40 s, a config knob in `main.py`) so it can be told
apart from a double press. With voice disabled, START acts instantly as before.

## Hardware

The Pi Zero 2 W has **no audio input** - add a **USB microphone** (via a
micro-USB OTG adapter) or an I2S MEMS mic. This is the one new piece of
hardware; it doesn't touch the buttons or the enclosure.

## Setup (on the Pi, from the repo root)

```
bash voice/setup_voice.sh        # installs vosk + sounddevice, downloads the model
```

Then in `main.py` set:
```
ENABLE_VOICE = True
BRAIN_URL    = "http://<your-PC-ip>:8090"
```
and run `python3 main.py`. If `vosk`/`sounddevice` or the model are missing,
voice just stays off and the clock runs as a plain timer.

The model folder (`voice/models/`) is gitignored - it's downloaded, not
committed. Other languages: pick a model at https://alphacephei.com/vosk/models
(use a *small* one for the Pi Zero 2 W).
