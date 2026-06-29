#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Brain (router + dispatch)  (pc_brain/brain.py)
# -----------------------------------------------------------------------------
#  Glues the two halves together: route() decides WHAT the user meant, then the
#  right ActionBackend for that domain DOES it. Kept separate from the HTTP
#  layer (brain_server.py) so the whole decision+dispatch path is unit-testable
#  with no sockets - see dev/test_voice_router.py.
# =============================================================================

from router import route


class Brain:
    def __init__(self, backends, llm=None):
        """backends: dict mapping domain ('home'/'timer') -> ActionBackend.
        llm: optional object with .route(text)->Intent|None (OllamaClient)."""
        self.backends = backends
        self.llm = llm

    def handle(self, text):
        """text -> {"text", "intent", "result"}. Never raises for ordinary
        failures; a bad command just yields a 'none' intent and a polite reply."""
        intent = route(text, self.llm)
        backend = self.backends.get(intent.domain)

        if backend is None:
            reply = self._fallback_reply(intent)
            result = {"ok": False, "reply": reply}
        else:
            result = backend.execute(intent)

        return {
            "text":   text,
            "intent": intent.to_dict(),
            "result": result,
        }

    @staticmethod
    def _fallback_reply(intent):
        if intent.domain == "none":
            return ("Sorry, I didn't catch a command. Try 'turn on the light' "
                    "or 'set 20 minutes'.")
        return f"No backend configured for '{intent.domain}' commands."
