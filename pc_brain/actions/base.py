#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - ActionBackend interface  (pc_brain/actions/base.py)
# -----------------------------------------------------------------------------
#  A backend turns an Intent into a real-world effect and returns a small result
#  dict. Keeping this interface tiny is what makes the executor swappable: the
#  brain only ever calls execute(intent), so Google Assistant can be replaced
#  with Home Assistant / direct bulb APIs later by writing one new file.
#
#  execute(intent) MUST return a dict shaped like:
#     {"ok": bool, "reply": str, ...extra fields a backend wants to expose...}
#  and MUST NOT raise for ordinary failures (return ok=False with a reply).
# =============================================================================


class ActionBackend:
    #: which domains this backend can handle, e.g. ("home",) or ("timer",).
    #: The brain uses this only for a friendly error if it's misconfigured.
    domains = ()

    def execute(self, intent):
        raise NotImplementedError

    @staticmethod
    def ok(reply, **extra):
        out = {"ok": True, "reply": reply}
        out.update(extra)
        return out

    @staticmethod
    def fail(reply, **extra):
        out = {"ok": False, "reply": reply}
        out.update(extra)
        return out
