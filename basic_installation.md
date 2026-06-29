# Exact Hour — Basic Installation Guide

A step-by-step guide to run **Exact Hour** (the countdown timer) on a
**Raspberry Pi Zero 2 W** driving a **MAX7219 8×32 dot-matrix display** with three
push buttons.

This guide assumes no prior Raspberry Pi experience. Follow it top to bottom.

---

## Table of Contents

1. [What You Need](#1-what-you-need)
2. [Flash Raspberry Pi OS](#2-flash-raspberry-pi-os)
3. [First Boot & Login](#3-first-boot--login)
4. [Enable SPI](#4-enable-spi)
5. [Install System Dependencies](#5-install-system-dependencies)
6. [Install the Python Libraries](#6-install-the-python-libraries)
7. [Wire the Hardware](#7-wire-the-hardware)
8. [Get the Code](#8-get-the-code)
9. [Run It](#9-run-it)
10. [Start Automatically on Boot (Optional)](#10-start-automatically-on-boot-optional)
11. [Controls Reference](#11-controls-reference)
12. [Troubleshooting](#12-troubleshooting)

**Voice Assistant:**

13. [Voice Assistant Overview](#13-voice-assistant-overview)
14. [Set Up the PC Brain (Your Computer)](#14-set-up-the-pc-brain-your-computer)
15. [Set Up the Pi Voice Front-End](#15-set-up-the-pi-voice-front-end)
16. [Control the Timer by Voice](#16-control-the-timer-by-voice)
17. [Connect Google Assistant for Smart Home](#17-connect-google-assistant-for-smart-home)
18. [Run the Brain Automatically (Optional)](#18-run-the-brain-automatically-optional)
19. [Voice Troubleshooting](#19-voice-troubleshooting)

---

## 1. What You Need

| Item | Notes |
|------|-------|
| Raspberry Pi Zero 2 W | With the 40-pin header soldered on. |
| microSD card | 8 GB or larger. |
| MAX7219 dot-matrix display | 4 chained 8×8 modules = **8×32** (FC16 "blue" modules are typical). |
| 3 × momentary push buttons | For UP, DOWN, START. |
| Jumper wires | Female–female work well with the FC16 module headers. |
| 5 V power supply | A good USB power source for the Pi. |

---

## 2. Flash Raspberry Pi OS

1. On your computer, download and install the **[Raspberry Pi Imager](https://www.raspberrypi.com/software/)**.
2. Insert the microSD card.
3. Open Imager and choose:
   - **Device:** Raspberry Pi Zero 2 W
   - **Operating System:** *Raspberry Pi OS Lite (64-bit)* — no desktop needed for this project
   - **Storage:** your microSD card
4. Click the **gear / "Edit Settings"** button before writing and set:
   - **Hostname:** e.g. `exacthour`
   - **Enable SSH** (use password authentication)
   - **Username & password** (remember these!)
   - **Wi-Fi SSID & password** (2.4 GHz network) and your **Wi-Fi country**
5. Click **Write** and wait for it to finish.

---

## 3. First Boot & Login

1. Put the microSD card into the Pi and power it on. Give it ~1–2 minutes on first boot.
2. From your computer, connect over SSH (replace the name/user with yours):

   ```bash
   ssh pi@exacthour.local
   ```

3. Update the system once you're in:

   ```bash
   sudo apt update && sudo apt full-upgrade -y
   ```

---

## 4. Enable SPI

The MAX7219 talks to the Pi over the **SPI** bus, which is off by default.

**Quick way (one command):**

```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

**Or the menu way:**

```bash
sudo raspi-config
```

Then go to **Interface Options → SPI → Yes**, finish, and reboot.

**Verify SPI is on** after the reboot — you should see two `spidev` devices:

```bash
ls -l /dev/spidev*
# expected: /dev/spidev0.0  /dev/spidev0.1
```

---

## 5. Install System Dependencies

The display library uses **Pillow** (image handling), which needs a few system
packages to build. Install them:

```bash
sudo apt install -y python3-pip python3-venv python3-dev \
    libjpeg-dev zlib1g-dev libfreetype6-dev libopenjp2-7
```

---

## 6. Install the Python Libraries

We install into a **virtual environment** (a clean, isolated folder for this
project's packages). This is the recommended, hassle-free approach on current
Raspberry Pi OS.

```bash
# Get the project. `git clone` creates a folder named after the repo
# (e.g. Exact-Hour). Do NOT `mkdir` one yourself first and clone into it -
# that leaves you with a confusing nested folder (Exact-Hour/Exact-Hour).
cd ~
git clone <your-repo-url>
cd Exact-Hour                 # use the folder name git just made (run `ls` to confirm)

# Create and activate a virtual environment INSIDE the project folder
python3 -m venv venv
source venv/bin/activate

# Install the libraries the script needs
pip install luma.led_matrix gpiozero lgpio spidev
```

> **No `git`, or copying the files some other way?** Skip the `git clone` above,
> get the code onto the Pi using [Section 8](#8-get-the-code), then `cd` into the
> project folder and run the `venv` + `pip install` steps.

> **What each package does**
> - `luma.led_matrix` — drives the MAX7219 over SPI (also pulls in `luma.core` + Pillow).
> - `gpiozero` — simple, debounced reading of the push buttons.
> - `lgpio` — the GPIO backend `gpiozero` uses on Raspberry Pi OS (Bookworm).
> - `spidev` — the SPI backend luma uses to reach the MAX7219. Without it the app
>   crashes at startup with `ModuleNotFoundError: No module named 'spidev'`.

You'll know the environment is active when your prompt starts with `(venv)`.
To leave it later, run `deactivate`.

<details>
<summary>Alternative: install system-wide (not recommended)</summary>

If you prefer not to use a virtual environment, you can install with:

```bash
sudo pip3 install luma.led_matrix gpiozero lgpio spidev --break-system-packages
```

The `--break-system-packages` flag is required because newer Raspberry Pi OS
protects the system Python. The virtual-environment method above avoids this.
</details>

---

## 7. Wire the Hardware

> ⚠️ **Power off the Pi before wiring** (`sudo shutdown -h now`, then unplug).

Pin numbers below use **BCM GPIO numbers** and the **physical pin number** on the
Pi's 40-pin header.

### Display (MAX7219 → Raspberry Pi)

| MAX7219 pin | Connect to (Pi) | BCM | Physical pin |
|-------------|-----------------|-----|--------------|
| `VCC` | 5 V | — | 2 (or 4) |
| `GND` | Ground | — | 6 |
| `DIN` | MOSI | GPIO10 | 19 |
| `CS`  | CE0  | GPIO8  | 24 |
| `CLK` | SCLK | GPIO11 | 23 |

### Buttons (each button → Pi)

Wire **one leg of each button to its GPIO pin** and **the other leg to any GND pin**.
No resistors are needed — the script turns on the Pi's internal pull-ups.

| Button | BCM | Physical pin |
|--------|-----|--------------|
| `UP`    | GPIO5  | 29 |
| `DOWN`  | GPIO6  | 31 |
| `START` | GPIO13 | 33 |
| (all) other leg → `GND` | — | 25, 30, 34, or 39 |

### ASCII wiring overview

```
   MAX7219                 Raspberry Pi Zero 2 W
  ┌────────┐              ┌──────────────────────┐
  │ VCC ───┼──────────────┤ 5V        (pin 2)     │
  │ GND ───┼──────────────┤ GND       (pin 6)     │
  │ DIN ───┼──────────────┤ GPIO10/MOSI (pin 19)  │
  │ CS  ───┼──────────────┤ GPIO8/CE0   (pin 24)  │
  │ CLK ───┼──────────────┤ GPIO11/SCLK (pin 23)  │
  └────────┘              │                        │
   [UP]    ───────────────┤ GPIO5     (pin 29)     │
   [DOWN]  ───────────────┤ GPIO6     (pin 31)     │
   [START] ───────────────┤ GPIO13    (pin 33)     │
   all button GNDs ───────┤ GND       (pin 25/30…) │
                          └──────────────────────┘
```

> **Note on display power:** 5 V gives the brightest output. The Pi's 3.3 V data
> signals usually drive these modules fine. If the display is glitchy, try powering
> `VCC` from **3.3 V (pin 1)** instead, or add a logic-level shifter.

---

## 8. Get the Code

**If you used `git clone` in [Section 6](#6-install-the-python-libraries), you
already have everything** (`main.py`, `remote_control.py`, `web_remote.html`,
and the optional `voice/` + `pc_brain/` folders, …) — skip ahead to
[Section 9](#9-run-it).

**Not using git? Copy the whole project folder from your computer with `scp`.**
Run this *on your computer* (not the Pi), from the directory that contains the
project folder:

```bash
scp -r Exact-Hour pi@exacthour.local:~/
```

> ⚠️ Copy the **entire folder**, not just `main.py`. The clock needs its
> companion files — e.g. without `remote_control.py` the phone/Wi-Fi control is
> silently skipped and port 8080 never opens.

---

## 9. Run It

Make sure the virtual environment is active, then run the script:

```bash
cd ~/Exact-Hour              # the folder git clone created
source venv/bin/activate     # if not already active
python main.py
```

The display fades in showing **`05:00`**. Use the buttons (see below) to set and
start your countdown. Press **Ctrl + C** to quit — the display clears on exit.

---

## 10. Start Automatically on Boot (Optional)

To make Exact Hour launch every time the Pi powers on, create a **systemd service**.

> ⚠️ **Use YOUR own username and folder name**, not `pi`/`exacthour`. If you log in
> as `doruk` and your project is in `~/Exact-Hour`, then your home path is
> `/home/doruk/Exact-Hour`. Getting this wrong is the #1 cause of a
> `status=203/EXEC` failure (systemd can't find the program). Run `whoami` to see
> your username and `pwd` (inside the project folder) to see the full path.

1. **Create the service file automatically.** This block fills in your real
   username, folder, and Python for you — just paste and run it
   (it assumes your project folder is `~/Exact-Hour`; change it if yours differs):

   ```bash
   PROJ="$HOME/Exact-Hour"
   PYBIN="$PROJ/venv/bin/python"
   [ -x "$PYBIN" ] || PYBIN="$(which python3)"   # fall back to system Python if no venv
   echo "User: $(whoami) | Folder: $PROJ | Python: $PYBIN"

   sudo tee /etc/systemd/system/exacthour.service >/dev/null <<EOF
   [Unit]
   Description=Exact Hour Countdown Timer
   After=multi-user.target

   [Service]
   Type=simple
   User=$(whoami)
   WorkingDirectory=$PROJ
   ExecStart=$PYBIN $PROJ/main.py
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   EOF
   ```

2. Enable and start it:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now exacthour.service
   ```

3. Check its status or logs anytime:

   ```bash
   systemctl status exacthour.service
   journalctl -u exacthour.service -f
   ```

> **If you see `status=203/EXEC`:** the `ExecStart`/`WorkingDirectory` path is
> wrong. Re-run the block in step 1 (it auto-detects the correct paths), then
> `sudo systemctl daemon-reload && sudo systemctl restart exacthour.service`.

---

## 11. Controls Reference

| Button | Action | What it does |
|--------|--------|--------------|
| **UP**    | Tap | +1 minute |
| **UP**    | Hold | Fast scroll up (speeds up the longer you hold) |
| **DOWN**  | Tap | −1 minute |
| **DOWN**  | Hold | Fast scroll down (speeds up the longer you hold) |
| **START** | Tap (when idle) | Start the countdown |
| **START** | Tap (when running) | Pause |
| **START** | Tap (when paused) | Resume |
| **START** | Tap (when finished) | Reset to 5:00 |
| **START** | **Double-tap** (any state) | **Talk to the AI** (see [Part II](#13-voice-assistant-overview)) |

Notes:
- Time can only be changed while **idle or paused** — it's locked while running.
- The display **never goes fully dark**; it dims to signal idle/paused states.
- At zero, it shows **`BITTI`** ("finished" in Turkish), blinking until you reset.
- **Double-tap** needs the voice assistant set up (a microphone + the PC brain
  from Part II) to actually do anything. While the listener is active, a single
  tap is held back by a fraction of a second so it can be told apart from a
  double-tap; if voice isn't active, a single tap is instant as above.

---

## 12. Troubleshooting

**Display shows garbage / mirrored / upside-down characters**
Edit the constants at the top of `main.py`:
- Try `BLOCK_ORIENTATION = 0` or `90` instead of `-90`.
- Try `ROTATE = 2` if the whole display is upside down.

**Display is too dim or too bright**
Adjust `INTENSITY_NORMAL` in `main.py` (range 0–15). Start at 5.

**`No such file or directory: '/dev/spidev0.0'`**
SPI isn't enabled. Re-do [Section 4](#4-enable-spi) and reboot.

**`ModuleNotFoundError: No module named 'luma'` (or `gpiozero`)**
The virtual environment isn't active, or the libraries aren't installed.
Run `source venv/bin/activate` then re-do [Section 6](#6-install-the-python-libraries).

**`ModuleNotFoundError: No module named 'spidev'`**
The SPI backend isn't installed in your environment. With the venv active, run:
```bash
pip install spidev
```

**`gpiozero` error about a pin factory / GPIO not available**
Make sure `lgpio` is installed in the same environment:
```bash
pip install lgpio
```

**Buttons do nothing**
- Confirm each button's other leg goes to **GND**.
- Confirm the GPIO numbers in `main.py` (`PIN_UP`, `PIN_DOWN`, `PIN_START`)
  match how you wired them.

**Display stays blank**
- Double-check `VCC`, `GND`, `DIN`, `CS`, and `CLK` wiring against
  [Section 7](#7-wire-the-hardware).
- Verify `CASCADED_DEVICES = 4` matches your number of 8×8 blocks.

---
---

# Part II — Voice Assistant

Part I gives you the working clock. This second part adds the device's other
half — a **voice assistant** you talk to by double-pressing the START button.
Its first job is **home automation** ("turn on the light"), and it grows from
there.

Set the sections up **in order** — each step is independently testable, so you
can verify the whole chain with *no* microphone and *no* smart devices first,
then wire the real hardware in. (If you ever want a deliberately voice-free
build, set `ENABLE_VOICE = False` in `main.py` and skip this part.)

---

## 13. Voice Assistant Overview

### How it works (and what runs where)

Speech recognition is cheap to run but the "understanding" is not, so the work
is split across **two machines**:

```
[ Raspberry Pi ]                         [ Your PC ]
  microphone                               brain_server.py
     │ you double-press START                 │
     ▼                                         ▼
  Vosk speech-to-text  ──recognized text──>  router  (keyword rules first,
  (offline, on the Pi)     over Wi-Fi          │       Ollama AI only if unsure)
     no AI here                                ▼
                                          action backend
                                   ┌──────────┼─────────────┐
                                   ▼          ▼             ▼
                                 mock     the clock     Google Assistant
                               (prints)   (this Pi)     (your smart home)
```

- **The Pi is just ears.** It records one short command, turns it into **text**
  with Vosk (free, offline, no account), and sends *only that text* to your PC.
- **Your PC is the brain.** A tiny keyword router handles obvious commands
  instantly; anything unclear is passed to a small local model in **Ollama**.
- **The "backend" is the hands** — and it's swappable. Start with `mock` (just
  prints what it *would* do), then point it at the clock and/or Google Assistant.

### Which machine does each section

| Section | Runs on | Needs |
|---------|---------|-------|
| 14 — PC brain | **Your PC** | Python, optionally Ollama |
| 15 — Pi voice front-end | **The Pi** | A USB microphone |
| 16 — Timer by voice | config on the PC | the clock from Part I |
| 17 — Google Assistant | config on the PC | a Google Home setup + a relay |

**Do them in order.** Get Section 14 working with the `mock` backend first — it
proves the whole chain end-to-end before you touch a microphone or any accounts.

### A note on privacy

Speech-to-text happens **offline on the Pi**. The only thing that leaves the Pi
is the recognized **text**, and only to **your own PC on your home Wi-Fi**. The
keyword rules and the Ollama model are local too. The *one* exception is the
optional Google Assistant backend in [Section 17](#17-connect-google-assistant-for-smart-home),
which (by design) sends the command on to Google so it can control your devices.

---

## 14. Set Up the PC Brain (Your Computer)

> All commands in this section run **on your PC**, not the Pi. (Windows is
> assumed here; on macOS/Linux use `python3` where it says `py` and `cp` where it
> says `copy`.)

### 14.1 Install Ollama and pull a small model

The AI fallback uses [**Ollama**](https://ollama.com) — a free app that runs
language models locally.

1. Download and install Ollama for your OS from <https://ollama.com>.
2. Pull a small model (open a terminal / PowerShell):

   ```powershell
   ollama pull llama3.2:3b
   ```

   > **On an older PC with ~4 GB RAM**, use the 1B model instead — it fits and is
   > faster, just a little less clever:
   > ```powershell
   > ollama pull llama3.2:1b
   > ```
   > Then set `"ollama_model": "llama3.2:1b"` in `config.json` (next step).

> **Ollama is optional.** Clear commands ("turn on the light", "set 20 minutes")
> are handled by the keyword rules and never touch Ollama. If you don't install
> it, set `"use_llm": false` in `config.json` and the assistant runs on rules
> alone.

### 14.2 Get the project onto your PC

If this repo is already on your PC, you're done. Otherwise `git clone` it (the
PC needs the `pc_brain/` folder; it does **not** need the luma/gpiozero libraries
— the brain is pure standard-library Python).

### 14.3 Configure

Copy the example config and (optionally) edit it. Defaults are fine for the first
mock test.

```powershell
cd <your-project-folder>
copy pc_brain\config.example.json pc_brain\config.json
```

Open `pc_brain\config.json` in any editor. For the first test, leave the
backends on `"mock"`:

```json
{
  "port": 8090,
  "use_llm": true,
  "ollama_model": "llama3.2:3b",
  "backends": { "home": "mock", "timer": "mock" }
}
```

(`config.json` is gitignored, so your local settings won't be committed.)

### 14.4 Start the brain

```powershell
py pc_brain\brain_server.py
```

You should see:

```
Exact Hour brain listening on http://0.0.0.0:8090/command
  backends: {'home': 'mock', 'timer': 'mock'}   llm: llama3.2:3b
```

Leave this window open — it prints what it hears and does.

### 14.5 Test it with the mock backend (no Pi, no mic)

In a **second** terminal on the same PC, send a command by hand:

```powershell
curl -X POST http://localhost:8090/command -H "Content-Type: application/json" -d "{\"text\":\"turn on the living room light\"}"
```

The brain window prints something like:

```
  heard: 'turn on the living room light'
   -> {'domain': 'home', 'action': 'on', ... }
   -> [MOCK] would turn ON : living room light
```

Try a few: `"set 20 minutes"`, `"pause"`, `"lights out"`. When this works, the
understanding half is proven. 🎉

### 14.6 Let the Pi reach your PC (firewall)

The Pi will POST to your PC's LAN address on port **8090**.

1. Find your PC's IP address:

   ```powershell
   ipconfig          # look for "IPv4 Address", e.g. 192.168.1.20
   ```

2. **Allow port 8090 through Windows Firewall** (run PowerShell *as
   Administrator*), or just click **Allow** if Windows prompts you the first time
   the brain starts:

   ```powershell
   New-NetFirewallRule -DisplayName "Exact Hour brain" -Direction Inbound -Protocol TCP -LocalPort 8090 -Action Allow
   ```

You'll use `http://<that-IP>:8090` as the Pi's `BRAIN_URL` in the next section.

---

## 15. Set Up the Pi Voice Front-End

> These commands run **on the Pi**.

### 15.1 Add a microphone

The Pi Zero 2 W has **no microphone input**, so add a **USB microphone**. The
Pi Zero's data USB port is a **micro-USB** socket, so you'll need a
**micro-USB (male) → USB-A (female) OTG adapter** to plug a normal USB mic in.

Plug it in, then confirm the Pi sees it:

```bash
arecord -l        # should list a "USB Audio" capture device
```

### 15.2 Install the voice dependencies and model

Activate the same virtual environment you made in [Section 6](#6-install-the-python-libraries),
then run the setup script from the project root. It installs the audio system
library, the Python packages (`vosk`, `sounddevice`), and downloads the small
offline English model (~50 MB) into `voice/models/`:

```bash
cd ~/Exact-Hour
source venv/bin/activate
bash voice/setup_voice.sh
```

> The model folder is **not** committed to git (it's large) — the script
> downloads it. For another language, pick a *small* model from
> <https://alphacephei.com/vosk/models> and set its path in `VOICE_MODEL_PATH`
> (next step).

### 15.3 Point the Pi at your PC in `main.py`

Voice is **on by default** (`ENABLE_VOICE = True`). The one thing you must set is
your PC's address, in the config block near the top of `main.py`:

```python
ENABLE_VOICE = True                          # already the default
BRAIN_URL    = "http://192.168.1.20:8090"    # <-- your PC's IP from Section 14.6
# VOICE_MODEL_PATH and DOUBLE_PRESS_WINDOW can stay at their defaults
```

- `DOUBLE_PRESS_WINDOW` (default `0.40` seconds) is how quickly you must press
  START twice for it to count as "talk to the AI". Increase it if double-presses
  are missed; decrease it if single presses feel laggy.

### 15.4 Run and try it

Make sure the **PC brain from Section 14 is running**, then start the clock:

```bash
python main.py
```

You should see `[voice] ready - double-press START to speak`. Now:

1. **Double-press the START button.** The Pi prints `[voice] listening...`.
2. Say a command, e.g. **"turn on the light"**.
3. Watch the **PC brain window** print the recognized text and the
   `[MOCK] would turn ON ...` line.

While it's listening and recognizing, the **countdown keeps ticking** — speech
runs on a background thread so the clock never freezes. A **single** START press
still starts/pauses the timer exactly as before.

> If voice can't start (missing model or mic), `main.py` simply prints why and
> runs as a normal clock — it never refuses to boot.

---

## 16. Control the Timer by Voice

Right now timer commands only print (mock). To make them drive the **real
clock**, switch the timer backend to `exact_hour` and tell it the clock's
address. Edit `pc_brain/config.json` **on your PC**:

```json
{
  "backends": { "home": "mock", "timer": "exact_hour" },
  "pi_clock_url": "http://192.168.1.50:8080"
}
```

- Use the **Pi's** IP for `pi_clock_url` (the clock serves its control API on
  port **8080** — the same one the phone app uses). Find it with `hostname -I`
  on the Pi.
- The clock must have `ENABLE_REMOTE = True` in `main.py` (it is by default).

Restart the brain (`Ctrl+C`, then `py pc_brain\brain_server.py`). Now, after a
double-press, these all work by voice:

| You say | It does |
|---------|---------|
| "set twenty five minutes" | sets the countdown to 25:00 |
| "give me ten more minutes" | adds 10 minutes |
| "pause" / "resume" | pause / resume |
| "how long is left" | reports the current time |
| "stop" / "reset" | resets the timer |

---

## 17. Connect Google Assistant for Smart Home

This is what makes **"turn on the light"** actually switch a real bulb, by
handing the command to **Google Assistant**, which controls whatever you've
already linked in the **Google Home** app.

> ### ⚠️ Read this first — this path has an expiry date
> The bridge this uses (**assistant-relay**) was **archived in April 2025** and
> relies on the **deprecated** Google Assistant SDK; **Google Assistant itself is
> being retired around March 2026** (replaced by Gemini). It works *for now*, but
> it **will** stop working. That's exactly why the assistant is built so the
> backend is **one swappable file**: when this breaks, you replace
> `pc_brain/actions/google_assistant.py` with, say, a **Home Assistant** or
> direct-bulb backend, and the Pi + brain stay untouched. Until then, this is the
> quickest "for now" option.

### What you need

- Your smart devices already added to the **Google Home** app (and working when
  you ask the Google app/speaker normally).
- A machine on your network to run **assistant-relay** (it needs **Node.js**).
  Your PC is fine.
- A free **Google Cloud** project with **OAuth (device) credentials** — the
  relay's setup walks you through this.

### Steps

1. Install **Node.js** (<https://nodejs.org>), then install and start
   **assistant-relay** by following its guide:
   <https://greghesp.github.io/assistant-relay/>. During setup you will:
   - create a Google Cloud project and download OAuth client credentials,
   - register a **user** name in the relay,
   - leave the relay running (it listens on a port, by default `3000`).
2. Note the relay's address (e.g. `http://192.168.1.20:3000`) and the user name.
3. Wire it into `pc_brain/config.json` **on your PC** and switch the `home`
   backend over:

   ```json
   {
     "backends": { "home": "google_assistant", "timer": "exact_hour" },
     "google_assistant": {
       "relay_url": "http://192.168.1.20:3000",
       "user": "yourname"
     }
   }
   ```

4. Restart the brain. Double-press START and say **"turn on the light"** — the
   linked device should switch. The brain echoes
   `Sent to Google Assistant: 'turn on the light'`.

> If the `home` backend is left on `google_assistant` but `relay_url` is blank,
> the assistant politely replies that it isn't configured (instead of erroring) —
> so you can always fall back to `"home": "mock"` while you sort the relay out.

---

## 18. Run the Brain Automatically (Optional)

So you don't have to start `brain_server.py` by hand every time:

### On Windows (your PC)

**Simplest — run at login.** Create a file `start-brain.bat` with:

```bat
@echo off
cd /d "C:\path\to\your\Exact-Hour"
py pc_brain\brain_server.py
```

Press `Win + R`, type `shell:startup`, Enter, and drop a **shortcut to that
`.bat`** into the folder that opens. It now launches when you log in. (For a
hidden, no-window service, use **Task Scheduler** → "Create Task" → trigger
"At log on" → action: your `.bat`, and tick "Run whether user is logged on or
not".)

> Make sure **Ollama** is also set to start on boot (its installer usually does
> this) so the AI fallback is available.

### On a Linux/macOS PC

Use a `systemd` user service (like [Section 10](#10-start-automatically-on-boot-optional))
or a `launchd` agent that runs `python3 pc_brain/brain_server.py`.

The **Pi** side (the clock + voice listener) auto-starts via the `systemd`
service you set up in [Section 10](#10-start-automatically-on-boot-optional) —
just make sure that was created *after* you set `ENABLE_VOICE = True`.

---

## 19. Voice Troubleshooting

**`[voice] disabled - missing dependency` on the Pi**
The venv isn't active or the packages aren't installed. Run
`source venv/bin/activate` then `pip install vosk sounddevice` (or re-run
`bash voice/setup_voice.sh`).

**`[voice] disabled - Vosk model not found`**
The model didn't download. Re-run `bash voice/setup_voice.sh`, or check that
`VOICE_MODEL_PATH` in `main.py` points at the unzipped model folder under
`voice/models/`.

**`arecord -l` shows no capture device / it hears nothing**
- Confirm the USB mic is seated in the **OTG adapter** and the Pi's **data** USB
  port (not the power-only port).
- List input devices Python can see:
  ```bash
  python3 -c "import sounddevice; print(sounddevice.query_devices())"
  ```
  Each device has an index. If the USB mic isn't the default input, make it the
  default ALSA capture device with a small `~/.asoundrc`, or note its index and
  test it directly:
  ```bash
  arecord -D plughw:1,0 -d 3 test.wav && aplay test.wav   # 1 = the USB card number from `arecord -l`
  ```

**The Pi reaches the brain but gets `{"ok": false, "error": ...}`**
- Check `BRAIN_URL` in `main.py` matches your **PC's** current IP (`ipconfig`).
- Make sure the **brain is running** and **port 8090 is allowed** through the
  PC's firewall ([Section 14.6](#14-set-up-the-pc-brain-your-computer)).
- Confirm both devices are on the **same Wi-Fi/LAN**.

**Ollama is slow, errors, or the PC runs out of memory**
- Use the **1B** model (`ollama pull llama3.2:1b`, set `"ollama_model"`).
- Ensure Ollama is running (`ollama list` should respond).
- Or set `"use_llm": false` to run on the keyword rules alone (no AI needed).

**Double-press isn't detected (or single presses feel laggy)**
Tune `DOUBLE_PRESS_WINDOW` in `main.py`: **larger** = easier double-presses but
laggier single presses; **smaller** = snappier single presses but you must tap
faster.

**It mishears words**
The small Vosk model trades accuracy for size. Speak clearly and keep commands
short ("lights off", "set twenty minutes"). The rules + Ollama still try to make
sense of near-misses; for better accuracy you can swap in a larger Vosk model on
a beefier Pi.

**"Smart home isn't configured" reply**
The `home` backend is `google_assistant` but `relay_url` is empty. Fill it in
([Section 17](#17-connect-google-assistant-for-smart-home)) or set
`"home": "mock"` to go back to printing.
