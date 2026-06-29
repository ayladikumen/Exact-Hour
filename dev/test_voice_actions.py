#!/usr/bin/env python3
# =============================================================================
#  Self-test for the exact_hour action backend  (no Pi, no hardware)
# -----------------------------------------------------------------------------
#  Proves the "timer by voice" path (Milestone 4): a timer Intent -> the
#  ExactHourBackend -> the REAL remote_control HTTP server -> a FakeTimer whose
#  state we then assert. This is the same FakeTimer + pump-loop the
#  remote_control self-test uses, so it exercises the genuine clock API.
#
#  Run:  py dev/test_voice_actions.py        (from the repo root)
# =============================================================================

import os
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "pc_brain"))

import remote_control as rc                             # noqa: E402
from router import Intent                                # noqa: E402
from actions.exact_hour import ExactHourBackend          # noqa: E402

# Defaults mirrored from main.py.
START_MINUTES = 5
MAX_MINUTES   = 270


# A pure in-memory clock with the same command surface remote_control drives
# (kept self-contained so this test depends only on remote_control + pc_brain).
class FakeTimer:
    def __init__(self):
        self.state = "IDLE"
        self.minutes = START_MINUTES
        self.seconds = 0

    def cmd_toggle(self):
        self.state = {"IDLE": "RUNNING", "RUNNING": "PAUSED",
                      "PAUSED": "RUNNING"}.get(self.state, self.state)
        if self.state == "FINISHED":
            self._reset()

    def cmd_start(self):
        if self.state == "IDLE":
            self.state = "RUNNING"

    def cmd_pause(self):
        if self.state == "RUNNING":
            self.state = "PAUSED"

    def cmd_resume(self):
        if self.state == "PAUSED":
            self.state = "RUNNING"

    def cmd_reset(self):
        self._reset()

    def cmd_adjust(self, delta):
        if self.state == "RUNNING":
            return                          # locked while running
        self.minutes = max(0, min(MAX_MINUTES, self.minutes + delta))
        self.seconds = 0

    def cmd_set(self, minutes, seconds=0):
        if self.state == "RUNNING":
            return
        self.minutes = max(0, min(MAX_MINUTES, minutes))
        self.seconds = max(0, min(59, seconds))

    def _reset(self):
        self.state, self.minutes, self.seconds = "IDLE", START_MINUTES, 0

    def status_dict(self):
        if self.minutes >= 60:
            disp = "{}:{:02d}:{:02d}".format(self.minutes // 60, self.minutes % 60, self.seconds)
        else:
            disp = "{:02d}:{:02d}".format(self.minutes, self.seconds)
        return {"state": self.state, "minutes": self.minutes, "seconds": self.seconds,
                "remaining_seconds": self.minutes * 60 + self.seconds,
                "display": disp, "max_minutes": MAX_MINUTES, "name": "Exact Hour"}


PORT = 8166
BASE = f"http://127.0.0.1:{PORT}"

_passed = 0
_failed = 0


def check(label, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}   {detail}")


def main():
    timer = FakeTimer()
    control = rc.RemoteControl()
    control.publish(timer.status_dict())

    stop = threading.Event()

    def loop():
        while not stop.is_set():
            rc.pump(timer, control)
            time.sleep(0.005)

    threading.Thread(target=loop, daemon=True).start()
    control.start_server(host="127.0.0.1", port=PORT)
    time.sleep(0.2)

    backend = ExactHourBackend(BASE)
    print("=== exact_hour backend self-test ===\n")

    # start with minutes -> set then start -> RUNNING at 20:00
    r = backend.execute(Intent("timer", action="start", minutes=20))
    check("start 20 -> ok + RUNNING", r["ok"] and timer.state == "RUNNING", (r, timer.state))
    check("start 20 -> 20:00 on the clock", timer.minutes == 20, timer.minutes)

    # pause / resume
    r = backend.execute(Intent("timer", action="pause"))
    check("pause -> PAUSED", r["ok"] and timer.state == "PAUSED", (r, timer.state))
    r = backend.execute(Intent("timer", action="add", minutes=5))
    check("add 5 while paused -> 25", timer.minutes == 25, timer.minutes)
    r = backend.execute(Intent("timer", action="resume"))
    check("resume -> RUNNING", r["ok"] and timer.state == "RUNNING", (r, timer.state))

    # status (read-only)
    r = backend.execute(Intent("timer", action="status"))
    check("status -> ok and reports a display",
          r["ok"] and "status" in r and r["status"].get("display"), r)

    # stop -> reset to idle/default
    r = backend.execute(Intent("timer", action="stop"))
    check("stop -> IDLE + default 5:00",
          r["ok"] and timer.state == "IDLE" and timer.minutes == 5, (r, timer.state, timer.minutes))

    # unreachable clock -> graceful fail, no raise
    dead = ExactHourBackend("http://127.0.0.1:1", timeout=1.0)
    r = dead.execute(Intent("timer", action="pause"))
    check("unreachable clock -> ok=False, no raise", r["ok"] is False, r)

    stop.set()
    control.stop_server()

    print(f"\n=== {_passed} passed, {_failed} failed ===")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
