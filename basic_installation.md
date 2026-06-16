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

1. Create the service file:

   ```bash
   sudo nano /etc/systemd/system/exacthour.service
   ```

2. Paste this (adjust the username if it isn't `pi`):

   ```ini
   [Unit]
   Description=Exact Hour Countdown Timer
   After=multi-user.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi/exacthour
   ExecStart=/home/pi/exacthour/venv/bin/python /home/pi/exacthour/main.py
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start it:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now exacthour.service
   ```

4. Check its status or logs anytime:

   ```bash
   systemctl status exacthour.service
   journalctl -u exacthour.service -f
   ```

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
