#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Timer backend  (pc_brain/actions/exact_hour.py)
# -----------------------------------------------------------------------------
#  Turns a "timer" Intent into an HTTP call to the Pi clock's EXISTING control
#  API (remote_control.py): /api/start|pause|resume|reset|set|adjust|status.
#  No new clock logic - this reuses exactly what the Android app already drives.
#
#  Mapping (router action -> clock endpoint):
#     start  : /api/set {minutes} if minutes given, then /api/start   (else /api/start)
#     add    : /api/adjust {delta=+minutes}
#     pause  : /api/pause
#     resume : /api/resume
#     stop   : /api/reset
#     status : GET /api/status
#
#  Stdlib only (urllib). Network failures return ok=False, never raise.
# =============================================================================

import json
import urllib.request
import urllib.error

from actions.base import ActionBackend


class ExactHourBackend(ActionBackend):
    domains = ("timer",)

    def __init__(self, base_url, timeout=3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout  = timeout

    def execute(self, intent):
        a = intent.action
        try:
            if a == "start":
                if intent.minutes is not None:
                    self._post("/api/set", {"minutes": int(intent.minutes), "seconds": 0})
                s = self._post("/api/start")
                return self.ok(self._say("Started", s), status=s)

            if a == "add":
                s = self._post("/api/adjust", {"delta": int(intent.minutes or 0)})
                return self.ok(self._say("Adjusted", s), status=s)

            if a == "pause":
                s = self._post("/api/pause")
                return self.ok(self._say("Paused", s), status=s)

            if a == "resume":
                s = self._post("/api/resume")
                return self.ok(self._say("Resumed", s), status=s)

            if a == "stop":
                s = self._post("/api/reset")
                return self.ok(self._say("Reset", s), status=s)

            if a == "status":
                s = self._get("/api/status")
                return self.ok(self._say("Status", s), status=s)

        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            return self.fail(f"Could not reach the clock at {self.base_url}: {exc}")

        return self.fail(f"Unknown timer action: {a!r}")

    # ----- internals ----------------------------------------------------------

    @staticmethod
    def _say(verb, status):
        disp = (status or {}).get("display", "?")
        state = (status or {}).get("state", "?")
        return f"{verb} the timer - {disp} ({state})."

    def _get(self, path):
        with urllib.request.urlopen(self.base_url + path, timeout=self.timeout) as r:
            return json.loads(r.read())

    def _post(self, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method="POST")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())
