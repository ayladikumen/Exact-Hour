#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - PC brain configuration  (pc_brain/config.py)
# -----------------------------------------------------------------------------
#  Defaults live here in code. A local config.json (gitignored, copy it from
#  config.example.json) overlays them so you can set your Pi's IP, Ollama model,
#  which backends to use, and your Google Assistant relay without editing code.
#
#  make_backend() builds a backend instance by name so brain_server can wire up
#  the configured executor for each domain.
# =============================================================================

import json
import os

# Defaults chosen so `python brain_server.py` works out-of-the-box on one PC:
# rules + Ollama for understanding, mock backends so nothing real is required.
DEFAULTS = {
    "host": "0.0.0.0",                 # listen on all interfaces (Pi must reach it)
    "port": 8090,                      # the Pi POSTs recognized text here

    "use_llm": True,                   # consult Ollama when the rules are unsure
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3.2:3b",     # any small local model; 1B works on 4 GB RAM

    # Which executor handles each domain. Start everything on "mock".
    "backends": {
        "home":  "mock",               # mock | google_assistant
        "timer": "mock",               # mock | exact_hour
    },

    # Used by the exact_hour backend - the Pi clock's address (remote_control.py).
    "pi_clock_url": "http://192.168.1.50:8080",

    # Used by the google_assistant backend - your assistant-relay instance.
    "google_assistant": {
        "relay_url": "",               # e.g. "http://192.168.1.20:3000"
        "user": "exacthour",
    },
}


def load(path=None):
    """Return DEFAULTS overlaid with config.json (if present). Shallow-merges
    the top level and the nested 'backends'/'google_assistant' dicts."""
    cfg = json.loads(json.dumps(DEFAULTS))      # deep copy of the defaults
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                user = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"[config] ignoring {path}: {exc}")
            user = {}
        for key, val in user.items():
            if isinstance(val, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(val)
            else:
                cfg[key] = val
    return cfg


def make_backend(name, cfg):
    """Build an ActionBackend instance from its config name. Imported lazily so
    a missing/optional dependency in one backend can't break the others."""
    if name == "mock":
        from actions.mock import MockBackend
        return MockBackend()
    if name == "exact_hour":
        from actions.exact_hour import ExactHourBackend
        return ExactHourBackend(cfg["pi_clock_url"])
    if name == "google_assistant":
        from actions.google_assistant import GoogleAssistantBackend
        ga = cfg.get("google_assistant", {})
        return GoogleAssistantBackend(relay_url=ga.get("relay_url"),
                                      user=ga.get("user", "exacthour"))
    raise ValueError(f"Unknown backend name: {name!r}")
