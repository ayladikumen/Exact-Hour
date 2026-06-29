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

## 7. Text-First AI Command Layer (`assistant.py`) - DEFERRED TO RELEASE 2

The text/voice AI assistant is **not part of Release 1** (clock + phone app).
Its files (`assistant.py`, the SmolLM2 model under `models/`, and `setup_ai_pi.sh`)
were removed from the main branch to keep the repo lean, and are preserved on the
**`release-2-ai`** branch. The original design notes (hybrid rule + SmolLM2 parser,
RAM budget, swap-in path) live in that branch's copy of this file. See `## 6.
Future Work` for the product vision this layer fulfils.
---

## 8. Local-Network Remote Control + Android App

### What it is

The clock can now be driven from a phone on the **same Wi-Fi network** — the
README's "companion" direction, done the simplest robust way: a tiny HTTP+JSON
server on the Pi and a minimalist native Android app that talks to it.

### Thread-safety model (the important bit)

The timer and the MAX7219 are touched by **exactly one thread** — the main loop.
The HTTP server runs in its own daemon thread and must never call timer/display
methods directly (two threads on the SPI bus = corruption). So:

```
phone --HTTP--> HTTP thread --enqueue Command--> CommandBus
main loop --drains, applies on ITS thread, publishes a status snapshot-->
HTTP thread --reads snapshot--> JSON reply
```

`remote_control.pump(timer, control)` is called once per main-loop iteration: it
drains queued commands, applies each via `apply_command()`, hands the fresh
status back to the waiting request, and publishes the latest snapshot for
`GET /api/status`. The HTTP side only ever enqueues + reads an immutable dict.

### Files added / changed

- `remote_control.py` — **NEW.** Stdlib-only (`http.server`, `json`, `queue`,
  `threading`, `socket`) so it has ZERO hardware deps and is unit-testable on a PC.
  Holds `RemoteControl` (queue + snapshot + server), `Command`, `apply_command()`,
  `pump()`, and `local_ip()`.
- `test_remote_control.py` — **NEW.** Spins up the real server against a
  `FakeTimer` and asserts the whole API. **20/20 pass** with `py test_remote_control.py`
  (runnable on the PC — this is the part validated without hardware).
- `main.py` — **CHANGED, additively + guarded.** New `cmd_*` methods + `status_dict()`
  on `ExactHour` (thin wrappers over the existing button logic, so app and buttons
  behave identically). `ENABLE_REMOTE`/`REMOTE_PORT` config; server started in
  `main()` inside a try/except; `pump()` called in `run()`. If the import or bind
  fails, or `ENABLE_REMOTE=False`, it runs hardware-only exactly as before.
- `android-app/` — **NEW folder.** Native Kotlin + Jetpack Compose app.

### The API (clock side)

`GET /api/status` · `POST /api/toggle|reset` · `POST /api/adjust {delta}` ·
`POST /api/set {minutes,seconds}`. Adjust/set obey the same "locked while RUNNING"
rule as the buttons. Status JSON:
`{state, minutes, seconds, remaining_seconds, display, max_minutes, name}`.

### Android app (`android-app/`)

- **Stack:** Kotlin 2.0.21 · AGP 8.13.2 · Gradle 8.13 · Compose BOM 2024.09.00 ·
  minSdk 26 / targetSdk 34. Networking via `HttpURLConnection` + bundled `org.json`
  (no Retrofit/OkHttp) and coroutines on `Dispatchers.IO`.
- **UI:** minimalist dark "instrument" — near-black, one amber accent (echoes the
  LED), monospace readout. Big context button (START/PAUSE/RESUME/NEW), presets
  (5/15/25/45), ± steppers (disabled while running), RESET, and a tappable
  connection pill that opens an IP/port dialog. IP/port persisted in SharedPreferences.
- **Permissions:** `INTERNET` + `usesCleartextTraffic="true"` (LAN HTTP, no TLS).
- **Build caveat:** open `android-app/` in Android Studio (it provisions Gradle +
  SDK). The binary `gradle-wrapper.jar` is intentionally not committed (can't ship
  as text); for CLI builds run `gradle wrapper --gradle-version 8.13` once.

### Status

- [x] `remote_control.py` + `test_remote_control.py` written; **20/20 tests pass** on PC.
- [x] `main.py` wired up (guarded, additive); `py_compile` clean.
- [x] Android app written; XML validated, code reviewed (no SDK on this machine to
      produce an APK — builds in Android Studio).
- [ ] Run `main.py` on the real Pi and confirm the phone controls it over Wi-Fi.
- [ ] Build/install the APK from Android Studio and test against the live clock.

---

## 9. Voice Assistant Layer (`voice/` on the Pi + `pc_brain/` on the PC)

### What it is

A voice front-end whose **first feature is home automation** ("turn on the
light"), expandable later. Design split (per the user): the **Pi does
speech-to-text only — no AI**; the **AI/intent lives on the main PC** (Ollama);
**actions go through a swappable backend** (Google Assistant "for now").

```
[Pi] mic --Vosk STT--> text  --POST /command-->  [PC] brain_server
        ^ double-press START                        router (rules first,
                                                     Ollama fallback) -> backend
                                       home -> mock | google_assistant
                                       timer-> mock | exact_hour (reuses the clock API)
```

### Trigger (no new hardware)

The middle **START** button: single press = start/pause/resume/reset (unchanged);
**double press = talk to the AI**, in ANY state. Implemented in
`ExactHour.handle_start_button()` — a single tap is deferred up to
`DOUBLE_PRESS_WINDOW` (~0.40 s) so a 2nd tap can be read as a double-press.
`ENABLE_VOICE=True` by default, but voice is only *active* if the listener
actually starts (mic + model present); if not, `self.listener` stays `None`, the
buffering is skipped, and START acts instantly — identical to the plain clock.

### Files

- **`voice/`** (Pi, optional/guarded like `rc`): `listener.py` (`VoiceListener` —
  daemon thread; `request_listen()` sets an Event; records → Vosk →
  `post_command()` POSTs to the brain). vosk/sounddevice imported lazily so
  `import voice` works without them. `setup_voice.sh` downloads the ~50 MB
  `vosk-model-small-en-us-0.15` into the gitignored `voice/models/`.
- **`main.py`** — CHANGED additively + guarded: `try: import voice`; config knobs
  `ENABLE_VOICE`/`BRAIN_URL`/`VOICE_MODEL_PATH`/`DOUBLE_PRESS_WINDOW`; listener
  built/started in `main()`; `handle_start_button()` replaces the raw
  `btn_start.tapped()` call in `run()`.
- **`pc_brain/`** (PC, **stdlib-only**, no pip deps): `router.py` (rule fast-path
  ported from the `release-2-ai` `assistant.py` + home-device rules; `Intent` has
  a `domain`), `ollama_client.py` (LLM fallback via `/api/chat`, `format:json`,
  only on unsure commands), `brain.py` (route → dispatch), `brain_server.py`
  (`POST /command`), `actions/{base,mock,exact_hour,google_assistant}.py`,
  `config.py` + `config.example.json` (→ gitignored `config.json`).

### Status

- [x] M1 PC brain + router + mock backend; **`dev/test_voice_router.py` 24/24**,
      live HTTP smoke OK. `dev/test_voice_listener.py` (Pi→brain contract) **5/5**.
- [x] M2 `voice/listener.py` + `main.py` double-press trigger written; `py_compile`
      clean; `import voice` works with no deps. `ENABLE_VOICE` now defaults **True**
      (degrades to plain clock if mic/model absent). (Mic/Vosk untested — needs the Pi.)
- [x] M4 `exact_hour` backend done; **`dev/test_voice_actions.py` 8/8** against the
      real `remote_control` server + `FakeTimer`. Switch `backends.timer` to use it.
- [ ] On the Pi: add USB mic, run `setup_voice.sh`, set `BRAIN_URL`, confirm
      double-press → speech → PC action, and the timer never stalls during STT.
- [ ] M3 Google Assistant backend (assistant-relay; archived/deprecated, ~Mar 2026)
      written + swappable, but untested end-to-end (needs a live relay + Google Home).
