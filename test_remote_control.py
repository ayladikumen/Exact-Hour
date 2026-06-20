#!/usr/bin/env python3
# =============================================================================
#  Self-test for remote_control.py  (runs on a normal PC - no hardware needed)
# -----------------------------------------------------------------------------
#  It spins up the REAL HTTP server from remote_control.py, but points it at a
#  FakeTimer that mimics the ExactHour state machine in memory (no LED, no SPI,
#  no GPIO). A tiny background thread plays the role of main.py's loop (it pumps
#  the command bus). Then we hit every endpoint with urllib and assert the JSON
#  contract the Android app relies on.
#
#  Run:  py test_remote_control.py
# =============================================================================

import json
import threading
import time
import urllib.request
import urllib.error

import remote_control as rc


# ----- defaults mirrored from main.py ----------------------------------------
START_MINUTES = 5
MAX_MINUTES   = 270


# =============================================================================
#  FakeTimer - the same command surface as ExactHour, pure in-memory.
#  Transitions match main.py: IDLE -> RUNNING -> PAUSED -> FINISHED.
# =============================================================================
class FakeTimer:
    def __init__(self):
        self.state   = "IDLE"
        self.minutes = START_MINUTES
        self.seconds = 0

    # --- the command surface remote_control.apply_command() calls ---
    def cmd_toggle(self):
        if self.state == "IDLE":
            self.state = "RUNNING"
        elif self.state == "RUNNING":
            self.state = "PAUSED"
        elif self.state == "PAUSED":
            self.state = "RUNNING"
        elif self.state == "FINISHED":
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
        if self.state in ("RUNNING", "FINISHED"):
            return
        self.minutes = max(0, min(MAX_MINUTES, self.minutes + delta))
        self.seconds = 0

    def cmd_set(self, minutes, seconds=0):
        if self.state in ("RUNNING", "FINISHED"):
            return
        self.minutes = max(0, min(MAX_MINUTES, minutes))
        self.seconds = max(0, min(59, seconds))

    def _reset(self):
        self.state   = "IDLE"
        self.minutes = START_MINUTES
        self.seconds = 0

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
            "name": "Exact Hour",
        }


# =============================================================================
#  Tiny test helpers
# =============================================================================
PORT = 8137
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


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=3) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def post(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# =============================================================================
#  Run the suite
# =============================================================================
def main():
    timer   = FakeTimer()
    control = rc.RemoteControl()
    control.publish(timer.status_dict())     # seed the snapshot before serving

    # Background "main loop": pump the bus ~200x/sec, like main.py does.
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            rc.pump(timer, control)
            time.sleep(0.005)

    threading.Thread(target=loop, daemon=True).start()
    control.start_server(host="127.0.0.1", port=PORT)
    time.sleep(0.2)                          # let the server bind

    print("=== remote_control.py self-test ===\n")

    # 1) initial status
    code, s = get("/api/status")
    check("GET /api/status -> 200", code == 200, f"got {code}")
    check("initial state IDLE", s.get("state") == "IDLE", s)
    check("initial display 05:00", s.get("display") == "05:00", s)
    check("status has all keys",
          all(k in s for k in ("state", "minutes", "seconds", "remaining_seconds",
                               "display", "max_minutes", "name")), s)

    # 2) set an absolute time while idle
    code, s = post("/api/set", {"minutes": 25, "seconds": 0})
    check("POST /api/set 25 -> running display 25:00",
          s.get("display") == "25:00" and s.get("minutes") == 25, s)

    # 3) adjust up/down while idle
    _, s = post("/api/adjust", {"delta": 5})
    check("adjust +5 -> 30:00", s.get("display") == "30:00", s)
    _, s = post("/api/adjust", {"delta": -10})
    check("adjust -10 -> 20:00", s.get("display") == "20:00", s)

    # 4) adjust clamps at the ceiling
    _, s = post("/api/set", {"minutes": 65})
    check("set 65 -> H:MM:SS format 1:05:00", s.get("display") == "1:05:00", s)
    _, s = post("/api/adjust", {"delta": 1000})
    check("adjust beyond max clamps to 270", s.get("minutes") == MAX_MINUTES, s)

    # 5) start (toggle) -> RUNNING, and adjust is now locked
    post("/api/set", {"minutes": 10})
    _, s = post("/api/toggle")
    check("toggle from idle -> RUNNING", s.get("state") == "RUNNING", s)
    _, s = post("/api/adjust", {"delta": 5})
    check("adjust ignored while RUNNING", s.get("minutes") == 10, s)

    # 6) pause / resume
    _, s = post("/api/toggle")
    check("toggle while RUNNING -> PAUSED", s.get("state") == "PAUSED", s)
    _, s = post("/api/adjust", {"delta": 5})
    check("adjust allowed while PAUSED -> 15", s.get("minutes") == 15, s)
    _, s = post("/api/resume")
    check("resume -> RUNNING", s.get("state") == "RUNNING", s)

    # 7) explicit pause/start endpoints
    _, s = post("/api/pause")
    check("pause endpoint -> PAUSED", s.get("state") == "PAUSED", s)
    _, s = post("/api/reset")
    check("reset -> IDLE 05:00", s.get("state") == "IDLE" and s.get("display") == "05:00", s)
    _, s = post("/api/start")
    check("start endpoint from idle -> RUNNING", s.get("state") == "RUNNING", s)

    # 7b) the built-in web remote is served at GET /
    req = urllib.request.Request(BASE + "/")
    with urllib.request.urlopen(req, timeout=3) as r:
        web_code = r.status
        web_ctype = r.headers.get("Content-Type", "")
        web_body = r.read().decode("utf-8", "replace")
    check("GET / serves the web remote HTML",
          web_code == 200 and "text/html" in web_ctype and "EXACT HOUR" in web_body,
          f"{web_code} {web_ctype}")

    # 8) unknown routes
    code, _ = get("/api/nope")
    check("unknown GET -> 404", code == 404, f"got {code}")
    code, _ = post("/api/nope")
    check("unknown POST -> 404", code == 404, f"got {code}")

    # 9) malformed body doesn't crash, just no-ops the value
    post("/api/reset")
    req = urllib.request.Request(BASE + "/api/adjust", data=b"{not json}", method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=3) as r:
        s = json.loads(r.read())
    check("malformed JSON body handled (no change)", s.get("minutes") == START_MINUTES, s)

    stop.set()
    control.stop_server()

    print(f"\n=== {_passed} passed, {_failed} failed ===")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
