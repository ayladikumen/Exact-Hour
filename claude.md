# claude.md — Project Save File & Memory

> This file is my persistent project memory for porting **Exact Hour** from the
> Arduino beta to the Raspberry Pi Zero 2 W. I update it as the project evolves.

---

## 1. Project Context (what the source files are)

I was given three source files. They are **not** three versions of the same thing —
they play different roles:

| File | Role | What I take from it |
|------|------|---------------------|
| `beta_v1.ino` | **THE BETA LOGIC** (source of truth) | The full countdown-timer behaviour I must reproduce in Python. |
| `README.md` | **Conceptual design / product vision** ("Exact Hour") | The *why* and the long-term direction (modes, single big button, voice). |
| `reference.txt` | **Hardware + library reference** (a sibling project, "DotNote") | The proven Raspberry Pi recipe: `luma.led_matrix`, `spi(...)`, `gpiozero`, and the MAX7219 wiring. |

**Key insight:** the README describes an *aspirational* single-button, count-up
product. The `.ino` beta is a *working* 3-button **countdown** timer. The task says
"retain all core functionalities **from the beta**", so the **`.ino` is the source of
truth** for this port. The README vision (count-up Focus mode, single button, voice)
is captured under "Future Work" — not built now.

---

## 2. Target Hardware

- **Compute:** Raspberry Pi Zero 2 W (Raspberry Pi OS, SPI enabled).
- **Display:** MAX7219 dot-matrix, **4 × 8×8 blocks = 32×8 pixels** (FC16 module).
- **Input:** 3 momentary push buttons (UP / DOWN / START), wired button→GND using the
  Pi's internal pull-ups (no external resistors — same as the beta's `INPUT_PULLUP`).

### Pinout (BCM numbering)
| Function | Pi GPIO | Physical pin |
|----------|---------|--------------|
| Display DIN (MOSI) | GPIO10 | 19 |
| Display CLK (SCLK) | GPIO11 | 23 |
| Display CS  (CE0)  | GPIO8  | 24 |
| Display VCC | 5V | 2 / 4 |
| Display GND | GND | 6 |
| Button UP    | GPIO5  | 29 |
| Button DOWN  | GPIO6  | 31 |
| Button START | GPIO13 | 33 |

---

## 3. Core Functionalities Extracted From the Beta (MUST keep)

These are the behaviours I lifted from `beta_v1.ino`. The Python port keeps **all** of them:

1. **State machine:** `IDLE → RUNNING → PAUSED → FINISHED` (+ reset back to IDLE).
2. **Buttons:**
   - UP / DOWN: tap = ±1 min; **hold = accelerating fast-scroll** with 3 tiers
     (≥0.4 s → ±1/150 ms, ≥1 s → ±5/150 ms, ≥3 s → ±10/120 ms).
   - START: Start / Pause / Resume / Reset (acts on release, like the beta).
   - UP+DOWN pressed together = no-op (mutual exclusion).
   - Adjusting is **locked while RUNNING** (must pause first); allowed in IDLE/PAUSED.
3. **Always-static display** (never scrolls), two formats:
   - `≥ 60 min` → `"H:MM:SS"` (compressed so it fits in 32 px)
   - `< 60 min` → `"MM:SS"` (centred)
4. **Intensity-based blink — display is never fully dark:**
   - NORMAL=5, DIM=2, PAUSED=3, PULSE=9 (0–15 scale, same as beta).
   - Asymmetric: long bright phase, short dim phase.
   - IDLE gently dims; RUNNING stays steady (the ticking seconds are the liveness cue);
     PAUSED does a slow low blink; FINISHED blinks "BITTI".
5. **Animations / cues** (minimalist):
   - Boot fade-in (0 → NORMAL).
   - Start/Resume = brightness **pulse up** ("go").
   - Pause = instant **dim drop** to PAUSED level.
   - Sub-minute crossing (60 min → <60 min) fires a one-time cue.
   - FINISHED = "BITTI" (Turkish for *finished*) fades in then blinks.
6. **Drift-free 1-second tick** (anchor += 1 s, not "sleep(1)").
7. **Limits / defaults:** start 5:00, ceiling `MAX_MINUTES = 270` (4 h 30 m), floor 0.

---

## 4. Architecture (Python port)

Single clean script: `main.py`. No frameworks, no metaprogramming — just a small
config block, a tiny bitmap font, and two classes.

```
main.py
├── CONFIG constants            # pins, brightness, timing, limits (mirrors beta #defines)
├── GLYPHS                      # tiny 7-px-tall bitmap font (0-9, ':', B, I, T)
├── class HoldButton            # wraps gpiozero.Button; adds tap + accelerating hold
│     ├── tapped()              #   START: fire once on release (= beta readTap)
│     └── poll()                #   UP/DOWN: tap + 3-tier accelerating repeat (= beta readButton)
├── class ExactHour             # the timer itself (state + display + behaviour)
│     ├── render() / show_time()/ show_bitti()
│     ├── set_intensity()       # maps beta's 0-15 onto luma contrast (level*16)
│     ├── start_pulse()/handle_pulse()   # non-blocking brightness pulse
│     ├── reset_blink()/handle_blink()   # the never-dark blink engine
│     ├── adjust()              # UP/DOWN logic + RUNNING lock
│     ├── on_start_tap()        # START state transitions
│     ├── tick()                # drift-free countdown + finish + sub-minute cue
│     └── run()                 # the main loop (mirrors Arduino loop())
└── main()                      # build device + buttons, run()
```

### Arduino → Python mapping
| Beta (Arduino / MD_Parola) | Python (Pi) |
|----------------------------|-------------|
| `MD_Parola` / `MD_MAX72xx` / `SPI.h` | `luma.led_matrix` (`max7219`) + `luma.core.interface.serial.spi` |
| `display.setIntensity(0-15)` | `device.contrast(level * 16)` (luma keeps the top 4 bits) |
| `display.print(...)` static | `luma.core.render.canvas` + custom `render()` (bitmap font) |
| `PA_OPENING / PA_WIPE / PA_MESH` | brightness **fade / pulse** cues (kept the *intent*, dropped Parola's effect engine) |
| `digitalRead` + `INPUT_PULLUP` | `gpiozero.Button(pull_up=True, bounce_time=...)` |
| `millis()` | `time.monotonic()` |
| manual debounce in `readButton` | `gpiozero` `bounce_time` handles debounce |

### Deliberate simplifications (documented on purpose)
- **Fonts:** the beta leans on MD_Parola's built-in font + `setCharSpacing`. luma's
  proportional fonts make exact width control fiddly, and `"H:MM:SS"` is right at the
  32 px edge. So I ship a **tiny self-contained 4-px-wide bitmap font** — pixel-perfect,
  guaranteed to fit, and dead simple to read (rows of `#` / `.`). No reliance on luma
  font internals.
- **Animations:** Parola's `PA_*` text effects don't exist in luma. I reproduce the
  *experience* (a clear but understated transition) with brightness fades/pulses, which
  are trivial and beginner-readable. The state machine and timing are 1:1 with the beta.
- **Colon blink:** the beta exposes a colon→space swap but never actually calls it; its
  real liveness signal is intensity. I keep the colon solid and blink via intensity,
  matching the beta's *actual* behaviour.

---

## 5. Roadmap / Status

- [x] **Step 1 — Ingest & understand** the `.ino`, `.md`, `.txt`.
- [x] **Step 2 — Initialise this `claude.md`** (roadmap + core functions + architecture).
- [x] **Step 3 — Write `main.py`** (full beta behaviour on luma + gpiozero) and self-review
      for SPI/MAX7219/import/memory issues.
- [x] **Step 4 — Write `basic_installation.md`** (flash, enable SPI, install libs, wiring, run).

### Self-review checklist applied to `main.py`
- [x] Intensity mapped correctly (0–15 → `contrast(level*16)`; 15→240, within 0–255).
- [x] Display redrawn **only on content change** (≤ 1×/sec), not every loop → no SPI spam, no image churn.
- [x] Blink/pause dimming done via `contrast()` (intensity register), no redraw needed.
- [x] All imports present: `time`, `luma.led_matrix.device.max7219`,
      `luma.core.interface.serial.spi/noop`, `luma.core.render.canvas`, `gpiozero.Button`.
- [x] Pull-ups + `bounce_time` set on buttons (no external resistors, debounced).
- [x] Drift-free tick via `monotonic` anchor; small `LOOP_SLEEP` keeps CPU idle.
- [x] Clean shutdown: `device.clear()` in `finally` on Ctrl-C.
- [x] No globals soup / no metaprogramming; everything commented for a beginner.

---

## 6. Future Work (from the README vision — NOT in this port)

- **Continuous Focus Mode** (count-up elapsed time).
- **Single large button** interaction model (short = start/pause, long = reset, double = switch mode).
- **Session logging** to local storage + export.
- **Voice module** (offline wake word + simple commands).
- Optional **RTC / NTP** for wall-clock features.

---

## 7. Text-First AI Command Layer (`assistant.py`)

### What it is

`assistant.py` is the **text-only prototype** of the README's "Voice-Triggered
Local AI" module (README §4). We build it text-first (you TYPE commands) to prove
the understand-and-act pipeline works before adding the hard parts (offline
speech + the LED matrix). It runs offline, with no cloud, ever.

### Architecture (three layers, each swappable without touching the others)

```
text input  →  parse()  →  Session  →  reply
 (today: input())          (timer model)   (today: print())
 (future: mic + wake word)                 (future: LED render() from main.py)
```

**`Session`** — timer state machine using the SAME state names as `ExactHour` in
`main.py` (`IDLE / RUNNING / PAUSED / FINISHED`) so the two merge trivially later.
`elapsed()` / `remaining()` are computed on demand from a `time.monotonic()`
anchor (drift-free, no background loop). Methods: `start()`, `pause()`,
`resume()`, `add_minutes()`, `stop()`, `elapsed()`, `remaining()`, `is_finished()`.

**The "brain" is a HYBRID** — most efficient, and deliberately leaves RAM free for
the future voice trigger:

1. **`rule_parse()`** — fast, offline, **zero extra RAM**. Extracts the first
   number, keyword-matches the action (flexible phrasing). The *primary* path.
2. **`LlmParser` (SmolLM2-135M)** — a tiny local LLM used **only as a fallback**
   when the rules return `unknown`. **Lazy-loaded**: if the rules always
   understand you, the model is never loaded and uses no RAM. Enabled with
   `--llm`; needs `llama-cpp-python` + the model file (i.e. on the Pi).

`parse(text, llm)` tries the rules first and consults the LLM only on a miss.

| Intent | Rule trigger keywords |
|--------|-----------------------|
| start (+ set goal) | `start`, `begin`, `go`, `make`, `set`, `run`, bare `N min` |
| stop  | `stop`, `end`, `finish`, `done`, `reset`, `cancel` |
| pause | `pause`, `hold`, `wait`, `freeze` |
| resume| `resume`, `continue`, `unpause`, `keep going` |
| status| `how long`, `how much`, `how am i`, `worked`, `left`, `remaining` |
| add   | `add`, `more`, `extend`, `plus`, `another` (+ number) |
| help / quit | `help`, `commands` / `exit`, `quit` |

Unrecognised input → friendly fallback, never a crash.

### The local AI model (committed with the repo)

- **Model:** `models/SmolLM2-135M-Instruct-Q4_0.gguf` (~92 MB), from
  [bartowski/SmolLM2-135M-Instruct-GGUF](https://huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF).
- **Why this one:** 135M is about the smallest *usable* instruct model; Q4_0 keeps
  it **under GitHub's 100 MB per-file limit** (so it commits in one normal `git
  push`, no Git LFS) and llama.cpp auto-repacks Q4_0 for the Pi's ARM cores.
- **Why not Ollama:** Ollama needs 4–8 GB RAM and will not run on 512 MB. We use
  `llama-cpp-python` (the llama.cpp Python binding) directly instead.

### RAM budget on the Pi Zero 2 W (512 MB) — leaving room for voice

| Consumer | Approx RAM |
|----------|-----------|
| Raspberry Pi OS Lite (headless) | ~100 MB |
| **Reserved for future wake-word listener** | ~80–120 MB |
| SmolLM2-135M Q4_0, `n_ctx=256`, mmap'd | ~150 MB *(only while a command is being understood)* |
| Timer app + Python | ~40 MB |

The hybrid + lazy-load design means the LLM is loaded only on a rule miss, and
wake-word detection and LLM inference run **sequentially** (you say the wake word,
*then* the command), so their peaks don't overlap. A 1 GB swap file
(`setup_ai_pi.sh`) absorbs any spikes.

### How to run

```bash
py assistant.py --selftest   # canned transcript, rule-based, no model needed (PC)
py assistant.py              # interactive, rule-based only (PC)
python assistant.py --llm    # interactive, with SmolLM2 fallback (on the Pi)
```

### Files added for this module

- `assistant.py` — the assistant (Session + hybrid parser + REPL + self-test).
- `models/SmolLM2-135M-Instruct-Q4_0.gguf` — the committed local AI model (~92 MB).
- `requirements.txt` — `llama-cpp-python` (rule-based path needs nothing).
- `setup_ai_pi.sh` — Pi-side setup: 1 GB swap + `llama-cpp-python` install.

### Future swap-in path

- **Speech in:** replace `input()` with an offline STT/wake-word engine (e.g.
  openWakeWord or Vosk) — it produces the same string `parse()` already eats.
- **Display out:** replace `print()` with `render()` from `main.py`.
- **Merge:** fold `Session` into `ExactHour` so buttons + voice share one timer.

### Status

- [x] `assistant.py` written; rule-based pipeline verified on PC (`--selftest`).
- [x] SmolLM2-135M Q4_0 model committed under `models/`.
- [x] `requirements.txt` + `setup_ai_pi.sh` for the Pi.
- [ ] Validate the `--llm` fallback on real Pi Zero 2 W hardware (latency/RAM).
- [ ] Add the offline wake-word + speech layer (voice stage).
