#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Mock backend  (pc_brain/actions/mock.py)
# -----------------------------------------------------------------------------
#  Does nothing real - it just prints (and returns) what it WOULD do. This is
#  the default backend so the whole speech -> router -> action chain can be
#  demoed and tested end-to-end before any microphone, Pi, or Google Cloud
#  setup exists. It accepts BOTH domains so it can stand in for either executor.
# =============================================================================

from actions.base import ActionBackend


class MockBackend(ActionBackend):
    domains = ("home", "timer", "none")

    def __init__(self, quiet=False):
        self.quiet = quiet           # tests set this to keep output clean
        self.calls = []              # record of intents seen (handy for tests)

    def execute(self, intent):
        self.calls.append(intent.to_dict())

        if intent.domain == "home":
            if intent.action in ("on", "off"):
                reply = "[MOCK] would turn {} : {}".format(
                    intent.action.upper(), intent.target or intent.phrase or "device")
            else:  # "raw"
                reply = "[MOCK] would say to Google Assistant: {!r}".format(
                    intent.phrase or intent.target or "")
        elif intent.domain == "timer":
            mins = "" if intent.minutes is None else f" ({intent.minutes} min)"
            reply = "[MOCK] would {} the timer{}".format(intent.action, mins)
        else:
            reply = "[MOCK] not understood - nothing to do"

        if not self.quiet:
            print(reply)
        return self.ok(reply)
