#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Browser DEMO server  (no Raspberry Pi, no LED, no GPIO)
# -----------------------------------------------------------------------------
#  Runs the REAL remote_control.py HTTP server against an in-memory timer that
#  actually counts down in real time, and serves the built-in web remote at
#  http://localhost:<port>/ . Open that in a browser to drive a live Exact Hour
#  timer end-to-end - the same API the Android app uses.
#
#  Run:  py demo_server.py            (binds 127.0.0.1:8731)
#        py demo_server.py 9000       (custom port)
# =============================================================================

import sys
import time
import threading

import remote_control as rc

START_MINUTES = 5
MAX_MINUTES   = 270


class DemoTimer:
    """Same command surface as main.py's ExactHour, but pure in-memory and it
    ticks down on its own so the browser shows a real countdown."""

    def __init__(self):
        self.state   = "IDLE"
        self.minutes = START_MINUTES
        self.seconds = 0
        self._anchor = 0.0          # monotonic time the next tick is measured from

    # --- the command surface remote_control.apply_command() calls ---
    def cmd_toggle(self):
        if self.state == "IDLE":
            self._run()
        elif self.state == "RUNNING":
            self.state = "PAUSED"
        elif self.state == "PAUSED":
            self._run()
        elif self.state == "FINISHED":
            self._reset()

    def cmd_start(self):
        if self.state == "IDLE":
            self._run()

    def cmd_pause(self):
        if self.state == "RUNNING":
            self.state = "PAUSED"

    def cmd_resume(self):
        if self.state == "PAUSED":
            self._run()

    def cmd_reset(self):
        self._reset()

    def cmd_adjust(self, delta):
        if self.state in ("RUNNING", "FINISHED"):
            return
        self.minutes = max(0, min(MAX_MINUTES, self.minutes + delta))
        self.seconds = 0

    def cmd_set(self, minutes, seconds=0):
        if self.state in ("RUNNING", "FINISHED"):
            return
        self.minutes = max(0, min(MAX_MINUTES, minutes))
        self.seconds = max(0, min(59, seconds))

    def _run(self):
        self.state   = "RUNNING"
        self._anchor = time.monotonic()

    def _reset(self):
        self.state   = "IDLE"
        self.minutes = START_MINUTES
        self.seconds = 0

    def tick(self):
        """Drift-free 1-second countdown, mirroring ExactHour.tick()."""
        if self.state != "RUNNING":
            return
        now = time.monotonic()
        if now - self._anchor < 1.0:
            return
        self._anchor += 1.0
        if self.seconds == 0:
            if self.minutes == 0:
                self.state = "FINISHED"
                return
            self.minutes -= 1
            self.seconds  = 59
        else:
            self.seconds -= 1

    def _time_text(self):
        if self.minutes >= 60:
            return "{}:{:02d}:{:02d}".format(self.minutes // 60, self.minutes % 60, self.seconds)
        return "{:02d}:{:02d}".format(self.minutes, self.seconds)

    def status_dict(self):
        return {
            "state": self.state,
            "minutes": self.minutes,
            "seconds": self.seconds,
            "remaining_seconds": self.minutes * 60 + self.seconds,
            "display": "BITTI" if self.state == "FINISHED" else self._time_text(),
            "max_minutes": MAX_MINUTES,
            "name": "Exact Hour (demo)",
        }


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8731

    timer   = DemoTimer()
    control = rc.RemoteControl()
    control.publish(timer.status_dict())

    stop = threading.Event()

    def loop():
        # Plays the role of main.py's run() loop: tick the clock, pump commands.
        while not stop.is_set():
            timer.tick()
            rc.pump(timer, control)
            time.sleep(0.02)

    threading.Thread(target=loop, daemon=True).start()

    # Bind locally only (no firewall prompt). Try a couple of ports.
    for candidate in (port, port + 1, port + 2):
        try:
            control.start_server(host="127.0.0.1", port=candidate)
            port = candidate
            break
        except OSError:
            continue
    else:
        raise SystemExit("Could not bind a demo port near {}.".format(port))

    print("Exact Hour demo is live -> http://localhost:{}/".format(port))
    print("Open it in a browser; press Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        control.stop_server()
        print("\nDemo stopped.")


if __name__ == "__main__":
    main()
