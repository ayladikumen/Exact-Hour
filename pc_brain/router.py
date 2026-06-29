#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Intent Router  (pc_brain/router.py)
# -----------------------------------------------------------------------------
#  This is the "understand what the user said" half of the brain. It turns a
#  line of recognized speech ("turn on the kitchen light", "set 20 minutes")
#  into a small, JSON-friendly Intent that the dispatcher can act on.
#
#  THE HYBRID (lean on purpose - the user did NOT want a heavyweight AI):
#    1. rule_route()  - instant, offline, zero-cost keyword matching. Handles
#                       the clear commands (lights on/off, start/stop a timer).
#    2. an LLM (Ollama) - OPTIONAL fallback, only consulted when the rules are
#                       unsure. Passed in by the caller; this module never
#                       imports or requires it, so router.py stays pure-Python
#                       and unit-testable on any PC with no Ollama running.
#
#  Intents have a `domain` so the dispatcher knows WHICH backend to use:
#    domain "home"  -> a smart-home command (-> Google Assistant / mock)
#    domain "timer" -> control the Exact Hour countdown (-> the Pi clock API)
#    domain "none"  -> we didn't understand it
#
#  The timer keyword logic is ported from the release-2-ai branch's
#  assistant.py rule_parse(), kept here so phrasing stays flexible.
# =============================================================================

import re


# =============================================================================
#  Intent - the small result object the router returns
# =============================================================================
class Intent:
    def __init__(self, domain, action=None, minutes=None, target=None,
                 phrase=None, source="rule"):
        self.domain  = domain      # "home" | "timer" | "none"
        self.action  = action      # home: on|off|raw ; timer: start|stop|pause|resume|status|add
        self.minutes = minutes     # int or None (timer only)
        self.target  = target      # best-effort device name for home (display/logging)
        self.phrase  = phrase      # the natural phrase to forward to Google Assistant (home)
        self.source  = source      # "rule" or "llm" - handy for debugging/logging

    def to_dict(self):
        return {
            "domain":  self.domain,
            "action":  self.action,
            "minutes": self.minutes,
            "target":  self.target,
            "phrase":  self.phrase,
            "source":  self.source,
        }

    def __repr__(self):
        return ("Intent(domain={domain}, action={action}, minutes={minutes}, "
                "target={target!r}, via={source})").format(**self.to_dict())


# =============================================================================
#  HOME (smart-home) rules
# -----------------------------------------------------------------------------
#  A line is a "home" command if it mentions a controllable device noun. The
#  action is on/off when that's clear, otherwise "raw" (we forward the whole
#  phrase and let Google Assistant figure it out, e.g. "make the light warmer").
# =============================================================================

# Device/appliance nouns that mark a home-automation command. Order matters only
# for which one we pick as the display `target` (longest sensible match first).
HOME_NOUNS = (
    "air conditioner", "television", "speakers", "speaker", "thermostat",
    "lights", "light", "lamps", "lamp", "bulb", "fan", "plug", "socket",
    "outlet", "heater", "kettle", "coffee", "blinds", "curtains", "curtain",
    "vacuum", "tv", "ac",
)

# Common room/location words we tack onto the target for a friendlier readout.
LOCATIONS = (
    "living room", "bedroom", "bathroom", "kitchen", "office", "hallway",
    "garage", "dining room", "study", "balcony", "garden",
)


def _first_noun(t):
    """Return the first HOME_NOUN found in the padded, lowercased text, or None.
    HOME_NOUNS is ordered so multi-word/longer nouns are tried first."""
    for noun in HOME_NOUNS:
        if re.search(r"\b" + re.escape(noun) + r"\b", t):
            return noun
    return None


def _home_target(t, noun):
    """Build a human-readable target like 'living room light' for logging/mock."""
    for loc in LOCATIONS:
        if loc in t:
            return f"{loc} {noun}"
    return noun


def _home_action(t):
    """Decide on/off from the text. 'off' wins if both somehow appear."""
    if re.search(r"\b(off|out)\b", t):
        return "off"
    if re.search(r"\b(on)\b", t):
        return "on"
    return None


# =============================================================================
#  TIMER rules  (ported from assistant.py rule_parse on the release-2-ai branch)
# -----------------------------------------------------------------------------
#  First keyword match wins, in this priority order. The first integer anywhere
#  in the line is taken as the minutes value (only "start"/"add" keep it).
# =============================================================================
_TIMER_KW = [
    ("add",    ("add", "more", "extend", "plus", "another", "increase")),
    ("stop",   ("stop", "end", "finish", "done", "reset", "cancel", "abort")),
    ("pause",  ("pause", "hold on", "hold", "wait", "freeze", "hang on")),
    ("resume", ("resume", "continue", "unpause", "keep going", "carry on")),
    ("status", ("how long", "how much", "how am i", "how is it", "how's it",
                "how are we", "worked", "elapsed", "remaining",
                "left", "status", "time is", "where am i")),
    ("start",  ("start", "begin", "make", "set", "launch", "run", "new session",
                "timer", "countdown")),
]

# A number followed by a time unit ("20 min", "20 minutes", "20 dakika").
_TIME_UNIT_RE = re.compile(r"\d+\s*(m|min|minute|minutes|dk|dakika)\b")


def _timer_rule(t):
    """Return an Intent in the 'timer' domain, or None if no timer keyword fits.
    `t` is already padded with spaces and lowercased."""
    num = re.search(r"\d+", t)
    minutes = int(num.group()) if num else None

    for action, words in _TIMER_KW:
        if any(w in t for w in words):
            keep = minutes if action in ("add", "start") else None
            return Intent("timer", action=action, minutes=keep, source="rule")

    # A bare number with a time unit ("20 min") = start that long.
    if minutes is not None and _TIME_UNIT_RE.search(t):
        return Intent("timer", action="start", minutes=minutes, source="rule")

    return None


# =============================================================================
#  rule_route() - the fast, offline, zero-cost interpreter (primary path)
# =============================================================================
def rule_route(text):
    """Map text -> Intent using keywords only. Returns domain 'none' when the
    rules aren't sure (the caller may then ask the LLM)."""
    t = " " + (text or "").lower().strip() + " "

    # 1) HOME first: if a device noun is present, it's a smart-home command.
    noun = _first_noun(t)
    if noun:
        action = _home_action(t)
        if action:
            return Intent("home", action=action, target=_home_target(t, noun),
                          phrase=(text or "").strip(), source="rule")
        # Device named but no clear on/off -> forward the raw phrase downstream.
        return Intent("home", action="raw", target=_home_target(t, noun),
                      phrase=(text or "").strip(), source="rule")

    # 2) TIMER next.
    timer_intent = _timer_rule(t)
    if timer_intent is not None:
        return timer_intent

    # 3) Rules unsure.
    return Intent("none", source="rule")


# =============================================================================
#  route() - the hybrid: rules first, LLM only when rules are unsure
# -----------------------------------------------------------------------------
#  `llm` is any object with a .route(text) -> Intent|None method (see
#  ollama_client.OllamaClient). Pass None to stay purely rule-based.
# =============================================================================
def route(text, llm=None):
    intent = rule_route(text)
    if intent.domain != "none":
        return intent                      # rules handled it -> no LLM call
    if llm is not None:
        guess = llm.route(text)            # ask the tiny model
        if guess is not None and guess.domain != "none":
            return guess
    return intent                          # still unsure
