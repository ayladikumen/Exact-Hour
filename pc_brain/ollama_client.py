#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Ollama Intent Client  (pc_brain/ollama_client.py)
# -----------------------------------------------------------------------------
#  The OPTIONAL LLM fallback for router.route(). It asks a small local model
#  served by Ollama (e.g. llama3.2:3b) to classify a command into the SAME
#  Intent shape the rules produce, but only when the rules were unsure.
#
#  We keep the model on a tight leash (the user wanted this lean, not a
#  "professional AI gen"):
#    * Ollama's "format": "json" forces a JSON object back - no prose to parse.
#    * temperature 0 for deterministic routing.
#    * A short system prompt + a few examples; we want ROUTING, not chat.
#
#  Stdlib only (urllib) so the PC brain has zero pip dependencies. If Ollama
#  isn't running or the call fails, route() falls back to "none" gracefully -
#  the assistant simply relies on the rules.
# =============================================================================

import json
import urllib.request
import urllib.error

from router import Intent


SYSTEM_PROMPT = (
    "You are the intent router for a small desk device that is BOTH a focus "
    "countdown timer and a voice remote for smart-home devices. Convert the "
    "user's spoken command into a single JSON object and nothing else.\n"
    "\n"
    "Schema:\n"
    '  {"domain": "home"|"timer"|"none", "action": string, '
    '"minutes": integer|null, "phrase": string|null}\n'
    "\n"
    "Rules:\n"
    '- domain "home": controlling a physical device (light, lamp, plug, fan, '
    "tv, heater, ac, speaker, blinds...). "
    'action is "on", "off", or "raw" (use "raw" when it is not a simple '
    "on/off, e.g. dimming or colour). "
    '"phrase" must be a clean command to say to Google Assistant, e.g. '
    '"turn on the living room light". minutes is null.\n'
    '- domain "timer": controlling the countdown timer. action is one of '
    '"start","stop","pause","resume","status","add". minutes is the number of '
    "minutes the user mentioned, else null. phrase is null.\n"
    '- domain "none": anything that is neither. action "none".\n'
    "\n"
    "Examples:\n"
    'turn on the light -> {"domain":"home","action":"on","minutes":null,'
    '"phrase":"turn on the light"}\n'
    'kill the bedroom lamp -> {"domain":"home","action":"off","minutes":null,'
    '"phrase":"turn off the bedroom lamp"}\n'
    'make the kitchen light warmer -> {"domain":"home","action":"raw",'
    '"minutes":null,"phrase":"make the kitchen light warmer"}\n'
    'give me twenty five minutes -> {"domain":"timer","action":"start",'
    '"minutes":25,"phrase":null}\n'
    'i am done -> {"domain":"timer","action":"stop","minutes":null,'
    '"phrase":null}\n'
    'what is the weather -> {"domain":"none","action":"none","minutes":null,'
    '"phrase":null}\n'
)


class OllamaClient:
    def __init__(self, base_url="http://localhost:11434",
                 model="llama3.2:3b", timeout=20.0):
        self.base_url = base_url.rstrip("/")
        self.model    = model
        self.timeout  = timeout

    def route(self, text):
        """Ask the model to classify `text`. Returns an Intent, or None on any
        failure (network down, bad JSON, Ollama not running)."""
        payload = {
            "model":  self.model,
            "format": "json",                # force a JSON object back
            "stream": False,
            "options": {"temperature": 0.0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": text or ""},
            ],
        }
        raw = self._post("/api/chat", payload)
        if raw is None:
            return None
        return self._parse(raw)

    # ----- internals ----------------------------------------------------------

    def _post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data,
                                     method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = json.loads(r.read())
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            return None                      # Ollama unreachable / bad reply
        # /api/chat returns {"message": {"content": "...json..."}, ...}
        return (body.get("message") or {}).get("content")

    @staticmethod
    def _parse(content):
        """Turn the model's JSON string into an Intent. Defensive: anything off
        spec collapses to a 'none' intent rather than raising."""
        try:
            obj = json.loads(content)
        except (ValueError, TypeError):
            return None
        if not isinstance(obj, dict):
            return None

        domain = obj.get("domain")
        if domain not in ("home", "timer"):
            return Intent("none", source="llm")

        action  = obj.get("action")
        minutes = obj.get("minutes")
        if not isinstance(minutes, int):
            minutes = None

        if domain == "home":
            if action not in ("on", "off", "raw"):
                action = "raw"
            phrase = obj.get("phrase") or ""
            return Intent("home", action=action, target=phrase or None,
                          phrase=phrase, source="llm")

        # timer
        if action not in ("start", "stop", "pause", "resume", "status", "add"):
            return Intent("none", source="llm")
        return Intent("timer", action=action, minutes=minutes, source="llm")
