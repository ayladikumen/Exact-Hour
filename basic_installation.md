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
13. [Text AI Assistant (Optional)](#13-text-ai-assistant-optional)

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
# Create a project folder and a virtual environment inside it
mkdir -p ~/exacthour
cd ~/exacthour
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install the libraries the script needs
pip install luma.led_matrix gpiozero lgpio
```

> **What each package does**
> - `luma.led_matrix` — drives the MAX7219 over SPI (also pulls in `luma.core` + Pillow).
> - `gpiozero` — simple, debounced reading of the push buttons.
> - `lgpio` — the GPIO backend `gpiozero` uses on Raspberry Pi OS (Bookworm).

You'll know the environment is active when your prompt starts with `(venv)`.
To leave it later, run `deactivate`.

<details>
<summary>Alternative: install system-wide (not recommended)</summary>

If you prefer not to use a virtual environment, you can install with:

```bash
sudo pip3 install luma.led_matrix gpiozero lgpio --break-system-packages
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

Put `main.py` into your project folder (`~/exacthour`).

**If the project is on GitHub:**

```bash
cd ~/exacthour
git clone <your-repo-url> repo
cp repo/main.py ~/exacthour/main.py
```

**Or copy it from your computer with `scp`:**

```bash
scp main.py pi@exacthour.local:~/exacthour/main.py
```

---

## 9. Run It

Make sure the virtual environment is active, then run the script:

```bash
cd ~/exacthour
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

Notes:
- Time can only be changed while **idle or paused** — it's locked while running.
- The display **never goes fully dark**; it dims to signal idle/paused states.
- At zero, it shows **`BITTI`** ("finished" in Turkish), blinking until you reset.

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

## 13. Text AI Assistant (Optional)

`assistant.py` lets you **type** commands in plain English instead of pressing
buttons — "make 20 min", "how long have I worked", "add 15 minutes", "stop".
It's the text-first version of the planned voice feature.

There are **two levels**. Start with Level 1 — it needs no setup at all.

### Level 1 — Just type commands (no install, works anywhere)

This works on the **Pi or your own PC**, with nothing extra to install.

1. Make sure you have the code (the same `assistant.py` and `models/` folder that
   came with the project — see [Section 8](#8-get-the-code)).
2. Run it:

   ```bash
   python assistant.py
   ```

   > On Windows, type `py assistant.py` instead of `python assistant.py`.

3. Type commands and press Enter. Try these:

   ```
   make 20 min
   how long have i worked
   add 15 minutes
   pause
   resume
   stop
   help
   exit
   ```

That's it — if you see replies like *"Session started…"*, it works. 🎉

**Want a quick demo without typing?** Run:

```bash
python assistant.py --selftest
```

It runs a list of example commands by itself and shows the answers.

### Level 2 — Turn on the local AI brain (Pi only)

Level 1 understands the common commands with simple rules. Level 2 adds a **tiny
offline AI model** (SmolLM2) so it also understands more unusual phrasings. The
AI runs **fully on the Pi — no internet, no cloud**.

> ⚠️ Do this **on the Raspberry Pi**, not your PC. It needs the Pi to compile.

1. Activate your virtual environment (the one from
   [Section 6](#6-install-the-python-libraries)):

   ```bash
   cd ~/exacthour
   source venv/bin/activate
   ```

2. Run the one-time setup script (adds extra memory + installs the AI library —
   this can take **10–20 minutes** on a Pi Zero, so be patient):

   ```bash
   bash setup_ai_pi.sh
   ```

3. Now run the assistant **with the AI turned on**:

   ```bash
   python assistant.py --llm
   ```

   You'll see *"Local AI ready"* if it worked. Type commands the same as before —
   now it can handle phrasings the simple rules would miss.

### Show the timer on the real LED matrix

By default the assistant only **prints** replies in the terminal. To make your
typed commands actually drive the **MAX7219 LED display** (the same one `main.py`
uses), add `--display`:

```bash
python assistant.py --display          # rules only, on the LED
python assistant.py --llm --display     # local AI + the LED
```

Now `make 20 min` shows `20:00` counting down on the matrix, `pause` freezes it,
`stop` clears it, and reaching the goal shows `BITTI` — all live while you type.

> The display needs the matrix wired up (Section 7) and runs on the Pi. Make sure
> `main.py` isn't running at the same time — only one program can use the display.
> `--display` only needs `luma.led_matrix` (no `gpiozero`/`lgpio`), so if you only
> want the screen working, `pip install luma.led_matrix` is enough.

> The AI model file (`models/SmolLM2-135M-Instruct-Q4_0.gguf`, ~92 MB) already
> comes with the project, so there is nothing to download.

### Troubleshooting the assistant

**`python: command not found`** → try `python3 assistant.py` (Pi) or `py assistant.py` (Windows).

**"Local AI unavailable…"** when using `--llm` → that's okay, it just falls back to
the simple rules and still works. To enable the AI, finish Level 2 above
(`bash setup_ai_pi.sh`).

**It feels slow with `--llm`** → the AI only runs when the simple rules are unsure,
and the Pi Zero is a small computer. For fastest use, run without `--llm`.
