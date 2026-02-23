// ============================================================
//  Production Countdown Timer — MD_Parola 8x32 LED Matrix
//  ────────────────────────────────────────────────────────
//  Buttons (pin → GND, no resistors):
//    BTN_UP    (pin 2) → +1 min tap, hold to fast-scroll
//    BTN_DOWN  (pin 3) → -1 min tap, hold to fast-scroll
//    BTN_START (pin 4) → Start / Pause / Resume / Reset
//
//  State machine:
//    IDLE     → time blinks (dim, not dark). UP/DOWN adjusts freely.
//    RUNNING  → colon blinks asymmetrically. UP/DOWN locked.
//    PAUSED   → display dims permanently + slow blink. UP/DOWN locked.
//    FINISHED → "BITTI" fades in, blinks. START resets.
//
//  Display: ALWAYS static (no scroll, ever).
//    ≥ 60 min → "H:MM:SS"  with setCharSpacing(0) to compress into 32px
//    < 60 min → "MM:SS"    centred, colon blinks
//
//  Blink design — intensity-based (never fully dark):
//    Bright state → intensity INTENSITY_NORMAL (5)
//    Dim state    → intensity INTENSITY_DIM    (2) — still visible, not harsh
//    Paused perm  → intensity INTENSITY_PAUSED (3) — constant dim, slow blink
//    Asymmetric:  800ms bright / 200ms dim — feels natural, less aggressive
//
//  Animations (minimalist):
//    Startup      → PA_OPENING wipe of initial time
//    IDLE→RUN     → quick brightness pulse up then settle
//    RUN→PAUSED   → instant dim drop to INTENSITY_PAUSED
//    PAUSED→RUN   → pulse back to full brightness
//    FINISHED     → PA_MESH dissolve-in of "BITTI" then blink
//    <60 min hit  → PA_WIPE transition (one-shot, then static)
// ============================================================

#include <MD_Parola.h>
#include <MD_MAX72xx.h>
#include <SPI.h>

// ── Hardware ──────────────────────────────────────────────────
#define HARDWARE_TYPE   MD_MAX72XX::FC16_HW
#define MAX_DEVICES     4
#define CS_PIN          10

// ── Button Pins ───────────────────────────────────────────────
#define BTN_UP          2
#define BTN_DOWN        3
#define BTN_START       4

// ── Timer Defaults & Limits ───────────────────────────────────
#define START_MINUTES   5
#define START_SECONDS   0
#define MAX_MINUTES     270    // 4 h 30 min ceiling

// ── Brightness Levels ─────────────────────────────────────────
#define INTENSITY_NORMAL  5    // Standard running brightness
#define INTENSITY_DIM     2    // "Off" phase of blink — dim not dark
#define INTENSITY_PAUSED  3    // Permanent dim level while paused
#define INTENSITY_PULSE   9    // Peak of the start/resume pulse

// ── Blink Timing (asymmetric: long bright, short dim) ─────────
#define BLINK_BRIGHT_MS   800  // Bright phase duration (IDLE/RUNNING)
#define BLINK_DIM_MS      200  // Dim phase duration
#define BLINK_PAUSE_MS   1400  // Bright phase when PAUSED (slower)
#define BLINK_PAUSE_DIM   300  // Dim phase when PAUSED

// ── Pulse Animation ───────────────────────────────────────────
#define PULSE_STEPS       6    // Brightness increments in pulse
#define PULSE_STEP_MS     18   // ms per pulse step (~108ms total)

// ── Button Timing ─────────────────────────────────────────────
#define DEBOUNCE_MS       50
#define HOLD_START_MS    400
#define TIER2_MS         1000
#define TIER3_MS         3000
#define REPEAT_T1_MS     150
#define REPEAT_T2_MS     150
#define REPEAT_T3_MS     120
#define STEP_T1            1
#define STEP_T2            5
#define STEP_T3           10

// ── Countdown ─────────────────────────────────────────────────
const unsigned long TICK_MS = 1000;

// ── Display Object ────────────────────────────────────────────
MD_Parola display = MD_Parola(HARDWARE_TYPE, CS_PIN, MAX_DEVICES);

// ============================================================
//  Timer State Machine
// ============================================================
enum TimerState { IDLE, RUNNING, PAUSED, FINISHED };
TimerState timerState = IDLE;

// ── Time Values ───────────────────────────────────────────────
int minutes = START_MINUTES;
int seconds = START_SECONDS;

// ── Countdown Clock ───────────────────────────────────────────
unsigned long previousMillis = 0;

// ── Blink State ───────────────────────────────────────────────
bool          blinkBright   = true;   // true = bright phase
unsigned long blinkPhaseEnd = 0;      // When current phase ends

// ── Sub-minute transition tracking ───────────────────────────
// Used to fire the PA_WIPE animation exactly once when the
// timer crosses from ≥60 min → <60 min for the first time.
bool crossedSubMinute = false;

// ── Animation State ───────────────────────────────────────────
// animating = true while a one-shot Parola animation is playing.
// Once displayAnimate() returns true (animation complete),
// animating is set false and the display returns to static mode.
bool animating = false;

// ── Pulse Animation State ─────────────────────────────────────
bool          pulsing       = false;
int           pulseStep     = 0;
unsigned long pulseStepTime = 0;
bool          pulseUp       = true;   // true = brightness rising

// ── Display Buffer ────────────────────────────────────────────
char timeBuffer[10]; // "H:MM:SS\0" = 8 bytes, padded to 10

// ============================================================
//  Button Struct
// ============================================================
struct Button {
  uint8_t       pin;
  bool          lastRaw;
  bool          state;
  unsigned long lastChangeMs;
  unsigned long pressedMs;
  unsigned long lastRepeatMs;
  bool          held;
};

Button btnUp    = { BTN_UP,    HIGH, HIGH, 0, 0, 0, false };
Button btnDown  = { BTN_DOWN,  HIGH, HIGH, 0, 0, 0, false };
Button btnStart = { BTN_START, HIGH, HIGH, 0, 0, 0, false };

// ============================================================
//  Hold Acceleration
// ============================================================
struct HoldTier { int step; unsigned long repeatMs; };

HoldTier getTier(unsigned long heldMs) {
  if (heldMs >= TIER3_MS) return { STEP_T3, REPEAT_T3_MS };
  if (heldMs >= TIER2_MS) return { STEP_T2, REPEAT_T2_MS };
  return                         { STEP_T1, REPEAT_T1_MS };
}

// ============================================================
//  buildTimeString(colonChar)
//  Fills timeBuffer. colonChar allows colon→space swap for blink.
//    ≥ 60 min → "H:MM:SS"  (colon always solid — colons are structural)
//    < 60 min → "MM:SS"    (colonChar toggles for blink effect)
// ============================================================
void buildTimeString(char colonChar = ':') {
  if (minutes >= 60) {
    int h = minutes / 60;
    int m = minutes % 60;
    sprintf(timeBuffer, "%d:%02d:%02d", h, m, seconds);
  } else {
    sprintf(timeBuffer, "%02d%c%02d", minutes, colonChar, seconds);
  }
}

// ============================================================
//  applyCharSpacing()
//  ≥ 60 min: compress to 0 so "H:MM:SS" fits in 32px.
//  < 60 min: standard spacing of 1 for clean "MM:SS" look.
//
//  Width estimate with default 5-col font, spacing 0:
//    "4:00:00" = 5+2+5+5+2+5+5 = 29px ✓ fits
//    "10:00:00" = 5+5+2+5+5+2+5+5 = 34px ✗ (won't happen: max=270min=4h30m)
// ============================================================
void applyCharSpacing() {
  display.setCharSpacing(minutes >= 60 ? 0 : 1);
}

// ============================================================
//  showStaticTime(colonChar)
//  Renders the current time statically on the matrix.
// ============================================================
void showStaticTime(char colonChar = ':') {
  applyCharSpacing();
  buildTimeString(colonChar);
  display.setTextAlignment(PA_CENTER);
  display.print(timeBuffer);
}

// ============================================================
//  showStaticBitti()
//  Renders "BITTI" statically (after entrance animation done).
// ============================================================
void showStaticBitti() {
  display.setCharSpacing(1);
  display.setTextAlignment(PA_CENTER);
  display.print("BITTI");
}

// ============================================================
//  startPulse(up)
//  Kicks off a non-blocking brightness pulse.
//  up=true: pulse from NORMAL up to PULSE then back.
//  up=false: pulse from current down to DIM then settle at NORMAL.
// ============================================================
void startPulse(bool up) {
  pulsing       = true;
  pulseUp       = up;
  pulseStep     = up ? 0 : PULSE_STEPS;
  pulseStepTime = millis();
}

// ============================================================
//  handlePulse()
//  Advances the brightness pulse animation each loop().
//  Non-blocking: only steps when PULSE_STEP_MS has elapsed.
// ============================================================
void handlePulse() {
  if (!pulsing) return;
  unsigned long now = millis();
  if (now - pulseStepTime < PULSE_STEP_MS) return;
  pulseStepTime = now;

  // Interpolate brightness: NORMAL(5) → PULSE(9) → NORMAL(5)
  int bright;
  if (pulseUp) {
    bright = INTENSITY_NORMAL + ((INTENSITY_PULSE - INTENSITY_NORMAL) * pulseStep / PULSE_STEPS);
    pulseStep++;
    if (pulseStep > PULSE_STEPS) { pulseUp = false; pulseStep = PULSE_STEPS; }
  } else {
    bright = INTENSITY_NORMAL + ((INTENSITY_PULSE - INTENSITY_NORMAL) * pulseStep / PULSE_STEPS);
    pulseStep--;
    if (pulseStep < 0) { pulsing = false; bright = INTENSITY_NORMAL; }
  }
  display.setIntensity(bright);
}

// ============================================================
//  resetBlink()
//  Always call after a content change to put the blink phase
//  back to BRIGHT so the user sees the update immediately.
// ============================================================
void resetBlink() {
  blinkBright   = true;
  blinkPhaseEnd = millis() + BLINK_BRIGHT_MS;
  display.setIntensity(INTENSITY_NORMAL);
}

// ============================================================
//  playAnimation(in, out)
//  Starts a one-shot Parola animation on the current timeBuffer.
//  animating is set true; loop() drives it until complete.
// ============================================================
void playAnimation(textEffect_t inFx, textEffect_t outFx, uint8_t speed = 30) {
  applyCharSpacing();
  display.displayText(timeBuffer, PA_CENTER, speed, 0, inFx, outFx);
  animating = true;
}

// ============================================================
//  playBittiAnimation()
//  Dissolve "BITTI" in. PA_MESH creates a sparse-dot fill
//  effect — looks striking without being loud.
// ============================================================
void playBittiAnimation() {
  display.setCharSpacing(1);
  display.displayText("BITTI", PA_CENTER, 40, 0, PA_MESH, PA_NO_EFFECT);
  animating = true;
}

// ============================================================
//  clampTimer()
// ============================================================
void clampTimer() {
  if (minutes < 0)           { minutes = 0; seconds = 0; }
  if (minutes > MAX_MINUTES)   minutes = MAX_MINUTES;
}

// ============================================================
//  adjustMinutes(delta)
//  Editable states: IDLE and PAUSED.
//  Locked during RUNNING — pause the timer first.
//  FINISHED redirects to IDLE, discards the adjustment.
// ============================================================
void adjustMinutes(int delta) {
  if (timerState == FINISHED) {
    timerState = IDLE;
    minutes    = START_MINUTES;
    seconds    = START_SECONDS;
    crossedSubMinute = false;
    buildTimeString();
    playAnimation(PA_WIPE, PA_NO_EFFECT, 20);
    resetBlink();
    return;
  }

  if (timerState == RUNNING) return; // Locked — must pause first

  // IDLE or PAUSED: apply the adjustment
  minutes += delta;
  clampTimer();

  if (timerState == PAUSED) {
    // Keep format flag in sync after editing.
    // Also reset seconds to 0 so the resumed tick is clean.
    crossedSubMinute = (minutes < 60);
    seconds = 0;
    display.setIntensity(INTENSITY_PAUSED); // Stay at paused brightness
  } else {
    resetBlink(); // IDLE: restart bright blink phase
  }

  showStaticTime(':');
}

// ============================================================
//  handleStartButton()
//  Drives all state transitions on BTN_START tap.
// ============================================================
void handleStartButton() {
  switch (timerState) {

    case IDLE:
      // ── Start countdown ───────────────────────────────────
      timerState       = RUNNING;
      crossedSubMinute = (minutes < 60); // Already sub-minute at start?
      previousMillis   = millis();       // First tick fires in exactly 1 s
      startPulse(true);                  // Bright flash = "go"
      resetBlink();
      showStaticTime(':');
      break;

    case RUNNING:
      // ── Pause ─────────────────────────────────────────────
      timerState = PAUSED;
      // Drop intensity immediately to INTENSITY_PAUSED — visual
      // cue that the clock has frozen.
      display.setIntensity(INTENSITY_PAUSED);
      blinkBright   = true;
      blinkPhaseEnd = millis() + BLINK_PAUSE_MS;
      break;

    case PAUSED:
      // ── Resume ────────────────────────────────────────────
      timerState     = RUNNING;
      previousMillis = millis(); // Resync: next tick in 1 s from now
      startPulse(true);          // Pulse signals resumption
      resetBlink();
      showStaticTime(':');
      break;

    case FINISHED:
      // ── Reset to IDLE ─────────────────────────────────────
      timerState       = IDLE;
      minutes          = START_MINUTES;
      seconds          = START_SECONDS;
      crossedSubMinute = false;
      buildTimeString();
      playAnimation(PA_OPENING, PA_NO_EFFECT, 25);
      resetBlink();
      break;
  }
}

// ============================================================
//  handleBlink()
//  Runs every loop(). Controls the asymmetric intensity blink.
//
//  IDLE    : full time display dims gently (5→2) — "ready"
//  RUNNING : colon blinks (space swap) + intensity rhythm
//  PAUSED  : slower blink at lower base intensity — "frozen"
//  FINISHED: handled by animating flag + blink after animation
// ============================================================
void handleBlink() {
  if (animating) return; // Let animation finish uninterrupted

  unsigned long now = millis();
  if (now < blinkPhaseEnd) return; // Current phase still active

  // Phase flip
  blinkBright = !blinkBright;

  switch (timerState) {

    case IDLE: {
      // Bright phase: normal display. Dim phase: drop intensity (not clear).
      int lvl = blinkBright ? INTENSITY_NORMAL : INTENSITY_DIM;
      display.setIntensity(lvl);
      if (blinkBright) showStaticTime(':');
      blinkPhaseEnd = now + (blinkBright ? BLINK_BRIGHT_MS : BLINK_DIM_MS);
      break;
    }

    case RUNNING: {
      // No blink while counting. The seconds ticking is the only
      // liveness signal needed. Intensity stays at INTENSITY_NORMAL
      // permanently. blinkPhaseEnd is set far ahead so this case
      // is never re-entered during a running countdown.
      display.setIntensity(INTENSITY_NORMAL);
      blinkPhaseEnd = now + 60000UL; // Revisit only after 60 s (never in practice)
      break;
    }

    case PAUSED: {
      // Slower, lower-contrast blink at INTENSITY_PAUSED base.
      // Signals "I'm still here but frozen" without being distracting.
      int lvl = blinkBright ? INTENSITY_PAUSED : INTENSITY_DIM;
      display.setIntensity(lvl);
      blinkPhaseEnd = now + (blinkBright ? BLINK_PAUSE_MS : BLINK_PAUSE_DIM);
      break;
    }

    case FINISHED: {
      // After BITTI animation completes, blink brightness on/off.
      // Use INTENSITY_DIM not clear — keeps it readable.
      int lvl = blinkBright ? INTENSITY_NORMAL : INTENSITY_DIM;
      display.setIntensity(lvl);
      blinkPhaseEnd = now + (blinkBright ? BLINK_BRIGHT_MS : BLINK_DIM_MS);
      break;
    }
  }
}

// ============================================================
//  readButton(btn, outStep)
//  Full debounce + accelerating hold. Returns 1=tap, 2=hold, 0=none.
// ============================================================
int readButton(Button &btn, int &outStep) {
  unsigned long now    = millis();
  bool          rawNow = digitalRead(btn.pin);

  if (rawNow != btn.lastRaw) {
    btn.lastRaw      = rawNow;
    btn.lastChangeMs = now;
  }
  if ((now - btn.lastChangeMs) < DEBOUNCE_MS) return 0;

  if (rawNow != btn.state) {
    btn.state = rawNow;
    if (btn.state == LOW) {
      btn.pressedMs    = now;
      btn.lastRepeatMs = now;
      btn.held         = false;
    } else {
      if (!btn.held) { outStep = STEP_T1; return 1; }
    }
  }

  if (btn.state == LOW) {
    unsigned long heldMs = now - btn.pressedMs;
    if (heldMs < HOLD_START_MS) return 0;
    btn.held = true;
    HoldTier tier = getTier(heldMs);
    if ((now - btn.lastRepeatMs) >= tier.repeatMs) {
      btn.lastRepeatMs = now;
      outStep          = tier.step;
      return 2;
    }
  }
  return 0;
}

// ============================================================
//  readTap(btn)
//  Tap-only detection for BTN_START. Fires on finger release.
// ============================================================
bool readTap(Button &btn) {
  unsigned long now    = millis();
  bool          rawNow = digitalRead(btn.pin);

  if (rawNow != btn.lastRaw) {
    btn.lastRaw      = rawNow;
    btn.lastChangeMs = now;
  }
  if ((now - btn.lastChangeMs) < DEBOUNCE_MS) return false;

  if (rawNow != btn.state) {
    btn.state = rawNow;
    if (btn.state == HIGH) return true; // Rising edge = tap complete
  }
  return false;
}

// ============================================================
//  initButton(btn)
//  Reads the actual pin state at boot so the button struct
//  starts in sync with reality.
//  FIX: Without this, the very first press needs a "settling"
//  transition from the default HIGH initialisation, causing the
//  first action to be dropped.
// ============================================================
void initButton(Button &btn) {
  bool actual       = digitalRead(btn.pin);
  btn.lastRaw       = actual;
  btn.state         = actual;
  btn.lastChangeMs  = millis();
}

// ============================================================
//  setup()
// ============================================================
void setup() {
  display.begin();
  display.setIntensity(0);   // Start dark for intro fade-in
  display.displayClear();

  pinMode(BTN_UP,    INPUT_PULLUP);
  pinMode(BTN_DOWN,  INPUT_PULLUP);
  pinMode(BTN_START, INPUT_PULLUP);

  // FIX: sync button structs to real pin state before first read
  initButton(btnUp);
  initButton(btnDown);
  initButton(btnStart);

  // ── Startup animation ─────────────────────────────────────
  // Fade display in from 0 to INTENSITY_NORMAL over ~300ms,
  // then play a PA_OPENING wipe of the initial time.
  // This is a blocking fade (only runs once at boot — acceptable).
  buildTimeString(':');
  for (int i = 0; i <= INTENSITY_NORMAL; i++) {
    display.setIntensity(i);
    delay(40); // 40 ms × 6 steps = 240 ms fade-in
  }

  // PA_OPENING splits the text reveal from centre outward —
  // clean, symmetric, appropriately understated.
  playAnimation(PA_OPENING, PA_NO_EFFECT, 30);

  timerState    = IDLE;
  resetBlink();
}

// ============================================================
//  loop()
// ============================================================
void loop() {
  unsigned long now = millis();

  // ── 1. Pulse animation driver ─────────────────────────────
  handlePulse();

  // ── 2. One-shot animation driver ─────────────────────────
  // When animating (intro, BITTI entrance, transitions) keep
  // driving displayAnimate() until it signals completion.
  if (animating) {
    if (display.displayAnimate()) {
      animating = false;

      // Post-animation: settle into correct static state
      if (timerState == FINISHED) {
        // BITTI animation done → show static BITTI and start blink
        showStaticBitti();
        resetBlink();
      } else {
        // Time animation done → show current time static
        display.setIntensity(INTENSITY_NORMAL);
        showStaticTime(':');
        resetBlink();
      }
    }
    // While animating: skip buttons and blink to avoid interference
    return;
  }

  // ── 3. START button ───────────────────────────────────────
  if (readTap(btnStart)) {
    handleStartButton();
  }

  // ── 4. UP / DOWN buttons ──────────────────────────────────
  int stepUp = 0, stepDown = 0;
  int resUp   = readButton(btnUp,   stepUp);
  int resDown = readButton(btnDown, stepDown);

  // Mutual exclusion: both pressed simultaneously = no-op
  bool upActive   = (resUp   != 0);
  bool downActive = (resDown != 0);

  if (upActive   && !downActive) adjustMinutes(+stepUp);
  if (downActive && !upActive)   adjustMinutes(-stepDown);

  // ── 5. Blink handler ──────────────────────────────────────
  handleBlink();

  // ── 6. Countdown tick ─────────────────────────────────────
  if (timerState != RUNNING) return;
  if (now - previousMillis < TICK_MS) return;

  previousMillis += TICK_MS; // Drift-free

  // Decrement
  if (seconds == 0) {
    if (minutes == 0) {
      // ── Timer expired ──────────────────────────────────
      timerState = FINISHED;
      display.setIntensity(INTENSITY_NORMAL); // Full bright for BITTI
      playBittiAnimation();
      return;
    }
    minutes--;
    seconds = 59;
  } else {
    seconds--;
  }

  // ── Sub-minute crossing animation ─────────────────────────
  // Fires exactly once when the timer drops below 60 minutes
  // for the first time. PA_WIPE slides old display away to
  // reveal the new "MM:SS" format — signals the mode change
  // without being jarring.
  if (!crossedSubMinute && minutes < 60) {
    crossedSubMinute = true;
    applyCharSpacing();
    buildTimeString(':');
    playAnimation(PA_WIPE, PA_NO_EFFECT, 25);
    return; // Loop will handle animation completion
  }

  // Normal tick: update static display and reset blink phase
  resetBlink();
  showStaticTime(':');
}
