#!/usr/bin/env python3
# =============================================================================
#  Self-test for the PC brain  (runs on a normal PC - no Ollama, no Pi, no mic)
# -----------------------------------------------------------------------------
#  Covers the two halves of pc_brain:
#    1. router.rule_route()/route() - does text land on the right Intent?
#    2. brain.Brain.handle()        - does the right backend get the Intent?
#
#  The LLM is a STUB (no Ollama needed) and the backends are a FakeBackend that
#  just records what it was asked to do. So this is fully offline + instant.
#
#  Run:  py dev/test_voice_router.py        (from the repo root)
# =============================================================================

import os
import sys

# This script lives in dev/; put the repo root AND pc_brain/ on the import path
# (pc_brain modules import each other by bare name, e.g. `from router import ...`).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "pc_brain"))

from router import rule_route, route, Intent          # noqa: E402
from brain import Brain                                # noqa: E402
from actions.base import ActionBackend                 # noqa: E402


# =============================================================================
#  Test doubles
# =============================================================================
class FakeBackend(ActionBackend):
    """Records the intents it's asked to execute; does nothing real."""
    def __init__(self, domain):
        self.domain = domain
        self.seen = []

    def execute(self, intent):
        self.seen.append(intent)
        return self.ok(f"[fake-{self.domain}] {intent.action}")


class StubLLM:
    """Stands in for OllamaClient.route(): returns a preset Intent (or None)."""
    def __init__(self, intent=None):
        self.intent = intent
        self.calls = 0

    def route(self, text):
        self.calls += 1
        return self.intent


# =============================================================================
#  Tiny harness
# =============================================================================
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


# =============================================================================
#  1) rule_route - HOME commands
# =============================================================================
def test_home_rules():
    print("\n-- home rules --")
    i = rule_route("turn on the light")
    check("'turn on the light' -> home/on", i.domain == "home" and i.action == "on", i)
    check("  phrase preserved for Google Assistant",
          i.phrase == "turn on the light", i)

    i = rule_route("turn off the bedroom lamp")
    check("'turn off the bedroom lamp' -> home/off",
          i.domain == "home" and i.action == "off", i)
    check("  target includes location", i.target == "bedroom lamp", i)

    i = rule_route("lights out")
    check("'lights out' -> home/off", i.domain == "home" and i.action == "off", i)

    i = rule_route("make the kitchen light warmer")
    check("'make the kitchen light warmer' -> home/raw",
          i.domain == "home" and i.action == "raw", i)

    i = rule_route("switch on the fan")
    check("'switch on the fan' -> home/on", i.domain == "home" and i.action == "on", i)


# =============================================================================
#  2) rule_route - TIMER commands
# =============================================================================
def test_timer_rules():
    print("\n-- timer rules --")
    i = rule_route("set 20 minutes")
    check("'set 20 minutes' -> timer/start 20",
          i.domain == "timer" and i.action == "start" and i.minutes == 20, i)

    i = rule_route("start a 25 minute timer")
    check("'start a 25 minute timer' -> timer/start 25",
          i.domain == "timer" and i.action == "start" and i.minutes == 25, i)

    i = rule_route("20 minutes")
    check("'20 minutes' -> timer/start 20",
          i.domain == "timer" and i.action == "start" and i.minutes == 20, i)

    i = rule_route("give me 15 more minutes")
    check("'give me 15 more minutes' -> timer/add 15",
          i.domain == "timer" and i.action == "add" and i.minutes == 15, i)

    i = rule_route("pause")
    check("'pause' -> timer/pause", i.domain == "timer" and i.action == "pause", i)

    i = rule_route("how long have i worked")
    check("'how long have i worked' -> timer/status",
          i.domain == "timer" and i.action == "status", i)

    i = rule_route("i'm done")
    check("'i'm done' -> timer/stop", i.domain == "timer" and i.action == "stop", i)


# =============================================================================
#  3) rule_route - unknown / none
# =============================================================================
def test_none_rules():
    print("\n-- none / unsure --")
    i = rule_route("what's the weather tomorrow")
    check("weather question -> none", i.domain == "none", i)
    i = rule_route("")
    check("empty string -> none", i.domain == "none", i)


# =============================================================================
#  4) route() hybrid - LLM only consulted when rules are unsure
# =============================================================================
def test_hybrid():
    print("\n-- hybrid (rules first, LLM fallback) --")
    llm = StubLLM(Intent("home", action="on", phrase="turn on the porch light",
                         source="llm"))

    # Rules already handle this -> LLM must NOT be called.
    i = route("turn on the light", llm)
    check("clear command skips the LLM", i.source == "rule" and llm.calls == 0, i)

    # Rules unsure -> LLM consulted and its intent used.
    i = route("illuminate the porch please", llm)
    check("unsure command consults the LLM", llm.calls == 1, f"calls={llm.calls}")
    check("  LLM intent is used", i.domain == "home" and i.source == "llm", i)

    # Rules unsure + no LLM -> stays none.
    i = route("illuminate the porch please", None)
    check("unsure + no LLM -> none", i.domain == "none", i)


# =============================================================================
#  5) Brain.handle - dispatches to the correct backend
# =============================================================================
def test_dispatch():
    print("\n-- dispatch to backends --")
    home  = FakeBackend("home")
    timer = FakeBackend("timer")
    brain = Brain({"home": home, "timer": timer}, llm=None)

    out = brain.handle("turn on the light")
    check("home command hits home backend",
          len(home.seen) == 1 and home.seen[0].action == "on", out)
    check("  result ok", out["result"]["ok"] is True, out)

    brain.handle("set 30 minutes")
    check("timer command hits timer backend",
          len(timer.seen) == 1 and timer.seen[0].minutes == 30, timer.seen)

    out = brain.handle("tell me a joke")
    check("unknown command -> no backend, polite reply",
          out["result"]["ok"] is False and len(home.seen) == 1 and len(timer.seen) == 1,
          out)


# =============================================================================
def main():
    print("=== pc_brain self-test ===")
    test_home_rules()
    test_timer_rules()
    test_none_rules()
    test_hybrid()
    test_dispatch()
    print(f"\n=== {_passed} passed, {_failed} failed ===")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
