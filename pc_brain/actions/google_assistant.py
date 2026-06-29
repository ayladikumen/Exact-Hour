#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Google Assistant backend  (pc_brain/actions/google_assistant.py)
# -----------------------------------------------------------------------------
#  Executes a "home" Intent by SPEAKING its phrase to Google Assistant, which
#  then controls whatever devices you already linked in the Google Home app
#  ("turn on the living room light"). That means we don't integrate each bulb
#  brand ourselves - Google does.
#
#  HOW (the practical "for now" path):
#    The cleanest way to send text commands to Google Assistant from a script is
#    a small relay server that wraps the Google Assistant SDK and exposes a REST
#    endpoint. The classic one is "assistant-relay"
#    (https://github.com/greghesp/assistant-relay): you run it once, do its
#    Google Cloud OAuth setup, register a user, and then POST a command:
#         POST {relay_url}/assistant   {"command": "...", "converse": false,
#                                       "user": "<name>"}
#    This backend just makes that POST. Point `relay_url`/`user` at your relay
#    in config.json.
#
#  !! SHELF LIFE (read this) !!
#    assistant-relay was ARCHIVED in April 2025 and rides on the DEPRECATED
#    Google Assistant SDK; Google Assistant itself is being retired (~March
#    2026, replaced by Gemini). So this path works "for now" but will break.
#    That is exactly why it lives behind ActionBackend: when it dies, write one
#    new file (e.g. a Home Assistant or direct-bulb backend) and the Pi STT +
#    Ollama brain stay untouched. Until then the default backend is `mock`.
#
#  Stdlib only (urllib). Misconfiguration / network errors return ok=False.
# =============================================================================

import json
import urllib.request
import urllib.error

from actions.base import ActionBackend


class GoogleAssistantBackend(ActionBackend):
    domains = ("home",)

    def __init__(self, relay_url=None, user="exacthour", timeout=10.0):
        self.relay_url = (relay_url or "").rstrip("/")
        self.user      = user
        self.timeout   = timeout

    def execute(self, intent):
        if not self.relay_url:
            return self.fail(
                "Google Assistant backend is not configured. Set "
                '"google_assistant": {"relay_url": "http://<host>:3000", '
                '"user": "<name>"} in config.json (run an assistant-relay '
                "instance first). Until then use the mock backend.")

        # Prefer the clean phrase the router/LLM built; fall back to raw text.
        command = (intent.phrase or intent.target or "").strip()
        if not command:
            return self.fail("No command phrase to send to Google Assistant.")

        try:
            resp = self._post("/assistant", {
                "command":  command,
                "converse": False,           # one-shot command, no follow-up turn
                "user":     self.user,
            })
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            return self.fail(f"Could not reach assistant-relay at {self.relay_url}: {exc}")

        # assistant-relay echoes a "response"/"success" field; surface it if present.
        spoken = ""
        if isinstance(resp, dict):
            spoken = resp.get("response") or resp.get("audio") or ""
        return self.ok(f"Sent to Google Assistant: {command!r}"
                       + (f" -> {spoken}" if spoken else ""), relay=resp)

    # ----- internals ----------------------------------------------------------

    def _post(self, path, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.relay_url + path, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read() or b"{}")
