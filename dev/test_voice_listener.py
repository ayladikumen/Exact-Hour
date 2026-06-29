#!/usr/bin/env python3
# =============================================================================
#  Self-test for the Pi voice listener's network path  (no mic, no Vosk, no Pi)
# -----------------------------------------------------------------------------
#  We can't exercise the microphone/Vosk part on a PC, but we CAN prove the
#  contract that matters: voice.post_command() -> the REAL PC brain server ->
#  the right mock action, over actual HTTP. We stand up brain_server with mock
#  backends and the LLM OFF (so no Ollama is needed), then POST through the same
#  helper the Pi uses.
#
#  Run:  py dev/test_voice_listener.py        (from the repo root)
# =============================================================================

import os
import sys
import threading
import time
from http.server import ThreadingHTTPServer

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "pc_brain"))

import voice                                   # noqa: E402  (Pi-side, stdlib-only import)
import config as cfg_mod                        # noqa: E402  (pc_brain/config.py)
import brain_server                             # noqa: E402  (pc_brain/brain_server.py)

PORT = 8191
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
    # Real brain, mock backends, LLM off -> fully offline + deterministic.
    cfg = cfg_mod.load()
    cfg["use_llm"] = False
    cfg["backends"] = {"home": "mock", "timer": "mock"}
    brain = brain_server.build_brain(cfg)

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT),
                                brain_server._make_handler(brain))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.2)

    print("=== voice listener network self-test ===\n")

    # 1) a home command travels Pi-helper -> brain -> mock home backend
    reply = voice.post_command(BASE, "turn on the kitchen light")
    check("post_command reaches the brain", isinstance(reply, dict) and "intent" in reply,
          reply)
    check("home command routed to home/on",
          reply.get("intent", {}).get("domain") == "home"
          and reply["intent"].get("action") == "on", reply)
    check("mock home reply came back",
          "MOCK" in (reply.get("result", {}).get("reply") or ""), reply)

    # 2) a timer command routes to the timer domain
    reply = voice.post_command(BASE, "set 20 minutes")
    check("timer command routed to timer/start 20",
          reply.get("intent", {}).get("domain") == "timer"
          and reply["intent"].get("minutes") == 20, reply)

    # 3) unreachable brain -> graceful error dict, no exception
    reply = voice.post_command("http://127.0.0.1:1", "turn on the light", timeout=1.0)
    check("unreachable brain returns ok=False, no raise",
          reply.get("ok") is False and "error" in reply, reply)

    httpd.shutdown()
    httpd.server_close()

    print(f"\n=== {_passed} passed, {_failed} failed ===")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
