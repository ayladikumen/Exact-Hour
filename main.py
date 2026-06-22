#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Countdown Timer for Raspberry Pi Zero 2 W + MAX7219 (8x32)
# -----------------------------------------------------------------------------
#  This is a Python port of the Arduino beta (beta_v1.ino). It keeps ALL of the
#  beta's behaviour, just expressed with Raspberry Pi libraries instead of
#  MD_Parola:
#
#    * State machine:  IDLE -> RUNNING -> PAUSED -> FINISHED  (+ reset to IDLE)
#    * 3 buttons:      UP / DOWN  (tap = +/-1 min, hold = accelerating scroll)
#                      START      (start / pause / resume / reset)
#    * Always-static display (it never scrolls), two formats:
#                      >= 60 min  ->  "H:MM:SS"
#                      <  60 min  ->  "MM:SS"
#    * Intensity-based blink  (the display is dimmed, never fully dark)
#    * Brightness pulse on start/resume, dim-drop on pause, fade-in on boot
#    * "BITTI" (Turkish for "FINISHED") shown when the countdown reaches zero
#    * Drift-free 1-second tick
#
#  Hardware libraries:
#    * luma.led_matrix  -> drives the MAX7219 over SPI
#    * gpiozero         -> reads the push buttons
#
#  The code is written to be read top-to-bottom by a beginner. Each block has a
#  comment explaining exactly what it does and why.
# =============================================================================

import sys                                           # stderr for fault logging
import time                                          # for timing (monotonic clock)
import traceback                                     # log remote-control faults

from luma.led_matrix.device import max7219           # the MAX7219 display driver
from luma.core.interface.serial import spi, noop     # SPI connection helpers
from luma.core.render import canvas                  # lets us draw onto the matrix
from gpiozero import Button                           # easy debounced GPIO buttons

# Optional local-network remote control (lets the Android app drive the clock).
# remote_control.py has NO hardware deps; the guard means main.py still runs as a
# hardware-only timer even if that file is removed.
try:
    import remote_control as rc
except ImportError:
    rc = None


# =============================================================================
#  CONFIGURATION  (all the "knobs" live here - mirrors the beta's #defines)
# =============================================================================

# ----- Display hardware -------------------------------------------------------
CASCADED_DEVICES  = 4      # four 8x8 blocks chained together = 32x8 pixels
BLOCK_ORIENTATION = -90    # -90 suits the common FC16 blue modules
ROTATE            = 0      # 0/1/2/3 - rotate the whole display if it's upside down

# ----- Brightness levels (0-15, exactly like the Arduino beta) ----------------
INTENSITY_NORMAL = 5       # standard running brightness
INTENSITY_DIM    = 2       # "off" phase of a blink - dim, not dark
INTENSITY_PAUSED = 3       # constant dim level while paused
INTENSITY_PULSE  = 9       # peak of the start/resume brightness pulse

# ----- Button GPIO pins (BCM numbering) ---------------------------------------
PIN_UP    = 5              # physical pin 29
PIN_DOWN  = 6              # physical pin 31
PIN_START = 13             # physical pin 33

# ----- Timer defaults & limits ------------------------------------------------
START_MINUTES = 5          # the timer powers on showing 5:00
START_SECONDS = 0
MAX_MINUTES   = 270        # ceiling = 4 h 30 m (matches the beta)

# ----- Blink timing in seconds (asymmetric: long bright, short dim) -----------
BLINK_BRIGHT_S    = 0.8    # bright phase for IDLE / FINISHED
BLINK_DIM_S       = 0.2    # dim phase for IDLE / FINISHED
BLINK_PAUSE_S     = 1.4    # bright phase while PAUSED (slower = "frozen")
BLINK_PAUSE_DIM_S = 0.3    # dim phase while PAUSED

# ----- Hold-to-scroll acceleration (3 tiers, just like the beta) --------------
HOLD_START_S = 0.40        # how long before a hold starts auto-repeating
TIER2_S      = 1.0         # after 1 s held -> medium speed
TIER3_S      = 3.0         # after 3 s held -> fast speed
REPEAT_T1_S  = 0.15        # repeat interval, tier 1
REPEAT_T2_S  = 0.15        # repeat interval, tier 2
REPEAT_T3_S  = 0.12        # repeat interval, tier 3
STEP_T1 = 1                # minutes added per repeat, tier 1
STEP_T2 = 5                # minutes added per repeat, tier 2
STEP_T3 = 10               # minutes added per repeat, tier 3
DEBOUNCE_S = 0.05          # button debounce window

# ----- Pulse animation --------------------------------------------------------
PULSE_STEPS  = 6           # number of brightness steps in the pulse
PULSE_STEP_S = 0.018       # time per pulse step (~108 ms up + ~108 ms down)

# ----- Loop / tick timing -----------------------------------------------------
TICK_S      = 1.0          # one countdown step = 1 second
LOOP_SLEEP  = 0.005        # tiny pause each loop so we don't peg the CPU
FADE_STEP_S = 0.04         # time per step of the boot / BITTI fade-in

# ----- Remote control (optional - control the clock from the Android app) -----
ENABLE_REMOTE = True       # serve the HTTP control API on the local Wi-Fi network
REMOTE_HOST   = "0.0.0.0"  # 0.0.0.0 = listen on every interface (so the phone can reach it)
REMOTE_PORT   = 8080       # the app connects to http://<this-pi-ip>:8080


# =============================================================================
#  TINY BITMAP FONT
# -----------------------------------------------------------------------------
#  Each glyph is 7 pixel-rows tall. A "#" is a lit LED, a "." is off.
#  Digits are 4 columns wide and the colon is 2 columns wide, which keeps the
#  widest string we ever show ("H:MM:SS", e.g. "4:30:00") at 30 px - it fits in
#  the 32 px display with a 1 px gap between characters.
#  We only need digits, a colon, and the letters B, I, T (for "BITTI").
# =============================================================================
GLYPH_HEIGHT = 7

GLYPHS = {
    "0": [".##.",
          "#..#",
          "#..#",
          "#..#",
          "#..#",
          "#..#",
          ".##."],
    "1": [".#..",
          "##..",
          ".#..",
          ".#..",
          ".#..",
          ".#..",
          "###."],
    "2": [".##.",
          "#..#",
          "...#",
          "..#.",
          ".#..",
          "#...",
          "####"],
    "3": ["###.",
          "...#",
          "...#",
          ".##.",
          "...#",
          "...#",
          "###."],
    "4": ["#..#",
          "#..#",
          "#..#",
          "####",
          "...#",
          "...#",
          "...#"],
    "5": ["####",
          "#...",
          "#...",
          "###.",
          "...#",
          "...#",
          "###."],
    "6": [".##.",
          "#...",
          "#...",
          "###.",
          "#..#",
          "#..#",
          ".##."],
    "7": ["####",
          "...#",
          "..#.",
          "..#.",
          ".#..",
          ".#..",
          ".#.."],
    "8": [".##.",
          "#..#",
          "#..#",
          ".##.",
          "#..#",
          "#..#",
          ".##."],
    "9": [".##.",
          "#..#",
          "#..#",
          ".###",
          "...#",
          "...#",
          ".##."],
    ":": ["..",
          "##",
          "##",
          "..",
          "##",
          "##",
          ".."],
    "B": ["###.",
          "#..#",
          "#..#",
          "###.",
          "#..#",
          "#..#",
          "###."],
    "I": ["###",
          ".#.",
          ".#.",
          ".#.",
          ".#.",
          ".#.",
          "###"],
    "T": ["###",
          ".#.",
          ".#.",
          ".#.",
          ".#.",
          ".#.",
          ".#."],
}


# =============================================================================
#  HoldButton - a thin wrapper around gpiozero.Button
# -----------------------------------------------------------------------------
#  gpiozero already gives us a clean, debounced "is it pressed?" reading.
#  On top of that we add the two behaviours the beta needed:
#
#    tapped()  -> True once, on release. Used for START (acts on every release).
#    poll()    -> tap on release, then an ACCELERATING auto-repeat while held.
#                 Used for UP / DOWN (tap = +/-1, hold = fast scroll).
#
#  Each physical button uses only ONE of these methods, so their internal
#  bookkeeping never clashes.
# =============================================================================
class HoldButton:
    def __init__(self, pin):
        # pull_up=True  -> button wired to GND, uses the Pi's internal pull-up
        # bounce_time   -> gpiozero debounces the input for us
        self._btn = Button(pin, pull_up=True, bounce_time=DEBOUNCE_S)
        self._was_pressed = False   # were we pressed last time we looked?
        self._pressed_at  = 0.0     # when the current press started
        self._last_repeat = 0.0     # when we last fired an auto-repeat
        self._held        = False   # has this press turned into a "hold"?

    def tapped(self):
        """Return True exactly once, on the release of a press (START button)."""
        is_down = self._btn.is_pressed
        result  = False
        if is_down and not self._was_pressed:
            self._was_pressed = True             # press just began
        elif not is_down and self._was_pressed:
            self._was_pressed = False            # press just ended -> that's a tap
            result = True
        return result

    def poll(self):
        """Return (event, step) for UP / DOWN.
        event is "tap", "hold", or None. step is how many minutes to change."""
        now     = time.monotonic()
        is_down = self._btn.is_pressed

        # --- edge: button just went down ---
        if is_down and not self._was_pressed:
            self._was_pressed = True
            self._pressed_at  = now
            self._last_repeat = now
            self._held        = False
            return (None, 0)

        # --- edge: button just came up ---
        if not is_down and self._was_pressed:
            self._was_pressed = False
            if not self._held:
                return ("tap", STEP_T1)          # a short press = single tap
            return (None, 0)                     # release after a hold = nothing

        # --- still being held down ---
        if is_down:
            held_for = now - self._pressed_at
            if held_for < HOLD_START_S:
                return (None, 0)                 # not long enough to count as a hold yet
            self._held = True
            step, repeat = self._tier(held_for)
            if now - self._last_repeat >= repeat:
                self._last_repeat = now
                return ("hold", step)            # time to fire one auto-repeat

        return (None, 0)

    @staticmethod
    def _tier(held_for):
        """Pick the (step, repeat-interval) for how long the button's been held."""
        if held_for >= TIER3_S:
            return (STEP_T3, REPEAT_T3_S)
        if held_for >= TIER2_S:
            return (STEP_T2, REPEAT_T2_S)
        return (STEP_T1, REPEAT_T1_S)


# =============================================================================
#  ExactHour - the timer itself
# -----------------------------------------------------------------------------
#  Holds all the state and the logic. The method names mirror the functions in
#  the Arduino beta so the two are easy to compare side by side.
# =============================================================================
class ExactHour:
    def __init__(self, device, btn_up, btn_down, btn_start, control=None):
        self.device    = device
        self.btn_up    = btn_up
        self.btn_down  = btn_down
        self.btn_start = btn_start
        self.control   = control         # RemoteControl bridge, or None if disabled

        # --- timer state ---
        self.state   = "IDLE"            # IDLE / RUNNING / PAUSED / FINISHED
        self.minutes = START_MINUTES
        self.seconds = START_SECONDS

        # --- countdown clock (drift-free) ---
        self.tick_anchor = 0.0           # when the next tick is measured from

        # --- blink state ---
        self.blink_bright    = True
        self.blink_phase_end = 0.0

        # --- pulse animation state ---
        self.pulsing    = False
        self.pulse_step = 0
        self.pulse_up   = True
        self.pulse_time = 0.0

        # Fires the one-time cue when we first drop below 60 minutes.
        self.crossed_sub_minute = False

        # Start dark + blank; the boot fade-in will bring it up.
        self.device.contrast(0)
        self.device.clear()

        # Seed the remote-control snapshot so GET /api/status works immediately,
        # even during the boot fade before the main loop's first publish.
        if self.control is not None:
            self.control.publish(self.status_dict())

    # ----- low-level display helpers -----------------------------------------

    def set_intensity(self, level):
        """Set MAX7219 brightness using the beta's 0-15 scale.
        luma's contrast() takes 0-255 and keeps only the top 4 bits
        (value // 16), so multiplying our level by 16 reproduces the same
        hardware brightness the Arduino used."""
        level = max(0, min(15, int(level)))
        self.device.contrast(level * 16)

    def render(self, message, gap=1):
        """Draw `message` static and horizontally centred on the matrix."""
        # First measure the total pixel width so we can centre it.
        width = sum(len(GLYPHS[ch][0]) for ch in message) + gap * (len(message) - 1)
        x0 = max(0, (self.device.width - width) // 2)
        y0 = (self.device.height - GLYPH_HEIGHT) // 2

        # canvas() gives us a drawing surface; leaving the block flushes it to
        # the LEDs. We only call this when the content actually changes.
        with canvas(self.device) as draw:
            x = x0
            for ch in message:
                rows = GLYPHS[ch]
                for row_index, row in enumerate(rows):
                    for col_index, pixel in enumerate(row):
                        if pixel == "#":
                            draw.point((x + col_index, y0 + row_index), fill="white")
                x += len(rows[0]) + gap     # advance past this glyph + the gap

    def time_text(self):
        """Build the time string in the correct format for the current value."""
        if self.minutes >= 60:
            hours = self.minutes // 60
            mins  = self.minutes % 60
            return "{}:{:02d}:{:02d}".format(hours, mins, self.seconds)
        return "{:02d}:{:02d}".format(self.minutes, self.seconds)

    def show_time(self):
        self.render(self.time_text())

    def show_bitti(self):
        self.render("BITTI")

    # ----- pulse animation (non-blocking) ------------------------------------

    def start_pulse(self):
        """Kick off a brightness pulse: NORMAL -> PULSE -> NORMAL."""
        self.pulsing    = True
        self.pulse_step = 0
        self.pulse_up   = True
        self.pulse_time = time.monotonic()

    def handle_pulse(self):
        """Advance the pulse by one step if enough time has passed."""
        if not self.pulsing:
            return
        now = time.monotonic()
        if now - self.pulse_time < PULSE_STEP_S:
            return
        self.pulse_time = now

        span = INTENSITY_PULSE - INTENSITY_NORMAL
        level = INTENSITY_NORMAL + span * self.pulse_step // PULSE_STEPS
        if self.pulse_up:
            self.pulse_step += 1
            if self.pulse_step > PULSE_STEPS:    # reached the top -> come back down
                self.pulse_up   = False
                self.pulse_step = PULSE_STEPS
        else:
            self.pulse_step -= 1
            if self.pulse_step < 0:              # back at the bottom -> done
                self.pulsing = False
                level = INTENSITY_NORMAL
        self.set_intensity(level)

    # ----- blink engine -------------------------------------------------------

    def reset_blink(self):
        """Put the blink back to the bright phase so an update is seen at once."""
        self.blink_bright    = True
        self.blink_phase_end = time.monotonic() + BLINK_BRIGHT_S
        self.set_intensity(INTENSITY_NORMAL)

    def handle_blink(self):
        """Run every loop. Drives the never-fully-dark intensity blink.
        Note: we only change brightness here - the pixels stay drawn, so there
        is no need to redraw the time."""
        now = time.monotonic()
        if now < self.blink_phase_end:
            return                       # current phase is still running
        self.blink_bright = not self.blink_bright   # flip bright <-> dim

        if self.state == "IDLE":
            level = INTENSITY_NORMAL if self.blink_bright else INTENSITY_DIM
            self.set_intensity(level)
            self.blink_phase_end = now + (BLINK_BRIGHT_S if self.blink_bright else BLINK_DIM_S)

        elif self.state == "RUNNING":
            # No blink while counting - the ticking seconds are liveness enough.
            # Push the next check far away so we never re-enter during a run.
            self.set_intensity(INTENSITY_NORMAL)
            self.blink_phase_end = now + 60.0

        elif self.state == "PAUSED":
            level = INTENSITY_PAUSED if self.blink_bright else INTENSITY_DIM
            self.set_intensity(level)
            self.blink_phase_end = now + (BLINK_PAUSE_S if self.blink_bright else BLINK_PAUSE_DIM_S)

        elif self.state == "FINISHED":
            level = INTENSITY_NORMAL if self.blink_bright else INTENSITY_DIM
            self.set_intensity(level)
            self.blink_phase_end = now + (BLINK_BRIGHT_S if self.blink_bright else BLINK_DIM_S)

    # ----- timer logic --------------------------------------------------------

    def clamp(self):
        """Keep the minutes inside [0, MAX_MINUTES]."""
        if self.minutes < 0:
            self.minutes = 0
            self.seconds = 0
        if self.minutes > MAX_MINUTES:
            self.minutes = MAX_MINUTES

    def adjust(self, delta):
        """Handle an UP / DOWN press. Editable only in IDLE and PAUSED."""
        if self.state == "FINISHED":
            # Any adjustment from the finished screen just resets to IDLE.
            self._reset_to_idle()
            return

        if self.state == "RUNNING":
            return                       # locked while running - pause first

        # IDLE or PAUSED: apply the change.
        self.minutes += delta
        self.clamp()

        if self.state == "PAUSED":
            # Keep the format flag in sync and zero the seconds for a clean resume.
            self.crossed_sub_minute = (self.minutes < 60)
            self.seconds = 0
            self.set_intensity(INTENSITY_PAUSED)     # stay at the paused brightness
        else:
            self.reset_blink()                       # IDLE: restart the bright blink

        self.show_time()

    def on_start_tap(self):
        """Handle a START press - this drives every state transition."""
        if self.state == "IDLE":
            # Start the countdown.
            self.state              = "RUNNING"
            self.crossed_sub_minute = (self.minutes < 60)
            self.tick_anchor        = time.monotonic()   # first tick in exactly 1 s
            self.start_pulse()                           # bright flash = "go"
            self.reset_blink()
            self.show_time()

        elif self.state == "RUNNING":
            # Pause: drop brightness immediately as a visual "frozen" cue.
            self.state = "PAUSED"
            self.set_intensity(INTENSITY_PAUSED)
            self.blink_bright    = True
            self.blink_phase_end = time.monotonic() + BLINK_PAUSE_S

        elif self.state == "PAUSED":
            # Resume: resync the clock and pulse to signal we're going again.
            self.state       = "RUNNING"
            self.tick_anchor = time.monotonic()
            self.start_pulse()
            self.reset_blink()
            self.show_time()

        elif self.state == "FINISHED":
            self._reset_to_idle()

    def _reset_to_idle(self):
        """Shared reset used by START and by adjusting from the FINISHED screen."""
        self.state              = "IDLE"
        self.minutes            = START_MINUTES
        self.seconds            = START_SECONDS
        self.crossed_sub_minute = False
        self.show_time()
        self.reset_blink()

    # ----- remote-control command surface ------------------------------------
    #  These mirror the physical buttons so the Android app and the buttons share
    #  EXACTLY the same behaviour. remote_control.pump() calls them from the main
    #  loop (this thread), so they are no less safe than a real button press.

    def cmd_toggle(self):
        """The big START button: start / pause / resume / clear-finished."""
        self.on_start_tap()

    def cmd_start(self):
        if self.state == "IDLE":
            self.on_start_tap()

    def cmd_pause(self):
        if self.state == "RUNNING":
            self.on_start_tap()

    def cmd_resume(self):
        if self.state == "PAUSED":
            self.on_start_tap()

    def cmd_reset(self):
        self._reset_to_idle()

    def cmd_adjust(self, delta):
        """+/- minutes. adjust() already enforces the 'locked while RUNNING' rule."""
        self.adjust(delta)

    def cmd_set(self, minutes, seconds=0):
        """Set an absolute time. Allowed in IDLE/PAUSED; clears a FINISHED screen
        first; ignored while RUNNING (the same lock the buttons obey)."""
        if self.state == "FINISHED":
            self._reset_to_idle()        # leave the finished screen -> now IDLE
        if self.state == "RUNNING":
            return                       # locked while counting; pause first
        self.minutes = minutes
        self.seconds = seconds
        self.clamp()
        if self.state == "PAUSED":
            self.crossed_sub_minute = (self.minutes < 60)
            self.seconds = 0             # clean resume, like adjust() does
            self.set_intensity(INTENSITY_PAUSED)
        else:
            self.reset_blink()
        self.show_time()

    def status_dict(self):
        """The JSON snapshot the Android app reads from GET /api/status."""
        display = "BITTI" if self.state == "FINISHED" else self.time_text()
        return {
            "state": self.state,
            "minutes": self.minutes,
            "seconds": self.seconds,
            "remaining_seconds": self.minutes * 60 + self.seconds,
            "display": display,
            "max_minutes": MAX_MINUTES,
            "name": "Exact Hour",
        }

    def tick(self):
        """Drift-free countdown step. Only does anything while RUNNING."""
        if self.state != "RUNNING":
            return
        now = time.monotonic()
        if now - self.tick_anchor < TICK_S:
            return
        self.tick_anchor += TICK_S       # advance the anchor, not "now" - no drift

        # Decrement one second.
        if self.seconds == 0:
            if self.minutes == 0:
                # Timer expired -> finish.
                self.state = "FINISHED"
                self.finish()
                return
            self.minutes -= 1
            self.seconds  = 59
        else:
            self.seconds -= 1

        # The first time we drop below 60 minutes, fire a one-time cue and
        # let the new "MM:SS" format appear.
        if not self.crossed_sub_minute and self.minutes < 60:
            self.crossed_sub_minute = True
            self.show_time()
            self.start_pulse()           # brightness pulse = "format changed" cue
            return

        # Normal tick: redraw the time once (intensity already steady at NORMAL).
        self.show_time()

    def finish(self):
        """Show 'BITTI' with a short fade-in, then hand over to the blink."""
        self.show_bitti()
        self._fade_to(INTENSITY_NORMAL)
        self.reset_blink()

    # ----- one-shot fades (only used at boot and at finish) -------------------

    def _fade_to(self, target):
        """Blocking brightness ramp from 0 to `target`. Used for boot + BITTI.
        Blocking is fine here because each fade happens only once."""
        for level in range(0, target + 1):
            self.set_intensity(level)
            time.sleep(FADE_STEP_S)

    def boot(self):
        """Draw the starting time and gently fade the display in."""
        self.show_time()
        self._fade_to(INTENSITY_NORMAL)
        self.state = "IDLE"
        self.reset_blink()

    # ----- main loop ----------------------------------------------------------

    def run(self):
        """The heart of the program - mirrors the Arduino loop()."""
        self.boot()
        try:
            while True:
                # 1) advance any in-progress brightness pulse
                self.handle_pulse()

                # 1b) apply any commands from the Android app (over Wi-Fi) on
                #     THIS thread, then publish the latest status for it to read.
                #     Guard it so a remote-control fault can never stop the clock.
                if self.control is not None:
                    try:
                        rc.pump(self, self.control)
                    except Exception:
                        traceback.print_exc(file=sys.stderr)

                # 2) START button (acts on release, like the beta)
                if self.btn_start.tapped():
                    self.on_start_tap()

                # 3) UP / DOWN buttons (tap + accelerating hold)
                up_event, up_step = self.btn_up.poll()
                dn_event, dn_step = self.btn_down.poll()
                up_active = up_event is not None
                dn_active = dn_event is not None
                # If both are pressed at once we do nothing (mutual exclusion).
                if up_active and not dn_active:
                    self.adjust(+up_step)
                elif dn_active and not up_active:
                    self.adjust(-dn_step)

                # 4) blink engine
                self.handle_blink()

                # 5) countdown tick
                self.tick()

                # 6) breathe - keep CPU usage low
                time.sleep(LOOP_SLEEP)
        except KeyboardInterrupt:
            pass                         # Ctrl-C is the normal way to quit
        finally:
            self.device.clear()          # leave the display blank on exit


# =============================================================================
#  main() - wire everything together and start
# =============================================================================
def main():
    # Open the SPI connection to the MAX7219. gpio=noop() tells luma we are not
    # using any extra GPIO pins for the display (chip-select is handled by SPI).
    serial = spi(port=0, device=0, gpio=noop())
    device = max7219(serial,
                     cascaded=CASCADED_DEVICES,
                     block_orientation=BLOCK_ORIENTATION,
                     rotate=ROTATE)

    # Create the three buttons.
    btn_up    = HoldButton(PIN_UP)
    btn_down  = HoldButton(PIN_DOWN)
    btn_start = HoldButton(PIN_START)

    # Optionally bring up the local-network remote control for the Android app.
    # If it can't start (e.g. port in use), we log it and run hardware-only.
    control = None
    if ENABLE_REMOTE and rc is not None:
        try:
            control = rc.RemoteControl()
            control.start_server(REMOTE_HOST, REMOTE_PORT)
            print("Exact Hour remote control is live at http://{}:{}".format(
                rc.local_ip(), REMOTE_PORT))
            print("Type that address into the Exact Hour Android app.")
        except OSError as exc:
            print("Remote control disabled (server could not start: {}).".format(exc))
            control = None

    # Build the timer and run it.
    app = ExactHour(device, btn_up, btn_down, btn_start, control=control)
    app.run()


if __name__ == "__main__":
    main()
