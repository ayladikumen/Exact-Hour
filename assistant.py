#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Text-First "Local AI" Command Layer  (assistant.py)
# -----------------------------------------------------------------------------
#  This is the text-only prototype of the README's "Voice-Triggered Local AI"
#  module. We build it text-first (you TYPE commands) so we can prove the
#  understand-and-act pipeline works BEFORE adding the hard parts (offline
#  speech-to-text + the LED matrix). The pipeline is:
#
#       text in  ->  parse() : the "brain"  ->  Session : the timer  ->  reply
#       (today: input())                                            (today: print())
#       (later:  microphone + wake word)                            (later:  LED matrix)
#
#  The two middle stages NEVER change when we add voice/LED later - that is the
#  whole reason we do text first.
#
#  THE "BRAIN" IS A HYBRID (most efficient, leaves RAM free for the voice trigger):
#    1. rule_parse()  - instant, offline, ZERO extra RAM. Handles the clear
#                       commands ("make 20 min", "stop", "how long...").
#    2. SmolLM2-135M   - a tiny local LLM (llama.cpp) used ONLY as a fallback when
#                       the rules are unsure. It is LAZY-LOADED: if the rules
#                       always understand you, the model is never loaded and uses
#                       no RAM at all. This keeps ~enough memory free on the
#                       512 MB Pi Zero 2 W for a future wake-word listener.
#
#  Runs on plain Python (rule-based) with NO dependencies, so you can test it on
#  your PC right now. The LLM fallback is optional and only kicks in if
#  `llama-cpp-python` is installed AND the model file is present (i.e. on the Pi).
# =============================================================================

import sys
import re
import time


# =============================================================================
#  CONFIGURATION
# =============================================================================

# --- Session limits (mirrors the beta timer in main.py) ----------------------
DEFAULT_MINUTES = 20          # what "start" with no number assumes
MAX_MINUTES     = 270         # 4 h 30 m ceiling, same as the beta

# --- Local LLM fallback (SmolLM2-135M, quantized GGUF) ------------------------
# The model lives in ./models so it is committed alongside the code in one repo.
MODEL_PATH   = "models/SmolLM2-135M-Instruct-Q4_0.gguf"
LLM_CTX      = 256            # tiny context = tiny KV-cache = less RAM (leaves room for voice)
LLM_THREADS  = 4             # Pi Zero 2 W has 4 cores; one-shot command, so brief full use is fine
LLM_MAX_TOK  = 24            # we only need a short "ACTION=.. MINUTES=.." line back


# =============================================================================
#  Session - the timer model (the "do the rest" half of the brain)
# -----------------------------------------------------------------------------
#  A small state machine, deliberately using the SAME state names as ExactHour
#  in main.py (IDLE / RUNNING / PAUSED / FINISHED) so the two are trivial to
#  merge once this drives the real LED display.
#
#  Time is measured from a time.monotonic() anchor and computed ON DEMAND, so
#  there is no background tick loop to run - perfect for a console prototype.
# =============================================================================
class Session:
    def __init__(self):
        self.state         = "IDLE"
        self.target_sec    = 0       # the goal length in seconds (0 = no goal set)
        self._anchor       = 0.0     # monotonic time the (current) run segment began
        self._banked       = 0.0     # elapsed seconds accumulated before the last pause
        self._announced_end = False  # so we announce "finished" only once

    # ----- elapsed / remaining (computed live from the anchor) ----------------
    def elapsed(self):
        run = (time.monotonic() - self._anchor) if self.state == "RUNNING" else 0.0
        return self._banked + run

    def remaining(self):
        return max(0.0, self.target_sec - self.elapsed())

    def is_finished(self):
        return self.target_sec > 0 and self.elapsed() >= self.target_sec

    # ----- commands -----------------------------------------------------------
    def start(self, minutes=None):
        """Begin a fresh session. If minutes given, that's the goal."""
        self.target_sec     = _clamp_minutes(minutes) * 60 if minutes else 0
        self._banked        = 0.0
        self._anchor        = time.monotonic()
        self.state          = "RUNNING"
        self._announced_end = False

    def pause(self):
        if self.state != "RUNNING":
            return False
        self._banked = self.elapsed()      # bank the time so far
        self.state   = "PAUSED"
        return True

    def resume(self):
        if self.state != "PAUSED":
            return False
        self._anchor = time.monotonic()    # restart the running segment
        self.state   = "RUNNING"
        return True

    def add_minutes(self, minutes):
        """Extend the goal by `minutes` (turns an open session into a goal one)."""
        self.target_sec += _clamp_minutes(minutes) * 60
        self._announced_end = False        # a new goal may push the end further out

    def stop(self):
        """End the session and return the total time worked (seconds)."""
        total = self.elapsed()
        self.state          = "IDLE"
        self.target_sec     = 0
        self._banked        = 0.0
        self._announced_end = False
        return total


def _clamp_minutes(m):
    """Keep a minute value sane: 1..MAX_MINUTES."""
    try:
        m = int(m)
    except (TypeError, ValueError):
        return DEFAULT_MINUTES
    return max(1, min(MAX_MINUTES, m))


# =============================================================================
#  Intent - the small result object the parser returns
# =============================================================================
class Intent:
    def __init__(self, action, minutes=None, source="rule"):
        self.action  = action      # start | stop | pause | resume | status | add | help | quit | unknown
        self.minutes = minutes     # an int, or None
        self.source  = source      # "rule" or "llm" - handy for debugging/the transcript

    def __repr__(self):
        return f"Intent({self.action}, minutes={self.minutes}, via={self.source})"


# =============================================================================
#  rule_parse() - the fast, offline, zero-RAM interpreter (primary path)
# -----------------------------------------------------------------------------
#  Pulls the first number out of the text, then matches action keywords. Word
#  order and exact phrasing don't matter, which is what makes "make 20 min",
#  "20 minutes", and "set a 20 minute timer and go" all land on the same intent.
#
#  Returns an Intent. action == "unknown" means "rules weren't sure" - the
#  caller may then ask the LLM.
# =============================================================================

# Keyword lists. First match (in this priority order) wins.
_KW = [
    ("quit",   ("exit", "quit program", "close", "goodbye")),
    ("help",   ("help", "commands", "what can you", "how do i")),
    ("add",    ("add", "more", "extend", "plus", "another", "increase")),
    ("stop",   ("stop", "end", "finish", "done", "reset", "cancel", "abort")),
    ("pause",  ("pause", "hold on", "hold", "wait", "freeze", "hang on")),
    ("resume", ("resume", "continue", "unpause", "keep going", "carry on")),
    ("status", ("how long", "how much", "how am i", "how is it", "how's it",
                "how are we", "worked", "elapsed", "remaining",
                "left", "status", "time is", "where am i")),
    ("start",  ("start", "begin", "go", "make", "set", "launch", "run", "new session")),
]


def rule_parse(text):
    t = " " + text.lower().strip() + " "

    # first integer anywhere in the line = the minutes value
    num = re.search(r"\d+", t)
    minutes = int(num.group()) if num else None

    for action, words in _KW:
        if any(w in t for w in words):
            # "add" / "start" want their number; the rest ignore it.
            if action in ("add", "start"):
                return Intent(action, minutes, "rule")
            return Intent(action, None, "rule")

    # A bare number with a time word ("20 min", "20 minutes") = start that long.
    if minutes is not None and re.search(r"\d+\s*(m|min|minute|minutes|dk|dakika)\b", t):
        return Intent("start", minutes, "rule")

    # A bare number on its own, nothing else = treat as "start N minutes".
    if minutes is not None and t.strip().isdigit():
        return Intent("start", minutes, "rule")

    return Intent("unknown", minutes, "rule")


# =============================================================================
#  LlmParser - the optional SmolLM2 fallback (lazy-loaded)
# -----------------------------------------------------------------------------
#  Only constructed the first time the rules are unsure. If `llama-cpp-python`
#  isn't installed or the model file is missing (e.g. on your PC), it stays
#  unavailable and the assistant just relies on the rules.
#
#  We ask the tiny model for ONE constrained line: "ACTION=.. MINUTES=.." and
#  parse it. A tight prompt + few-shot examples keep a 135M model on the rails.
# =============================================================================
class LlmParser:
    SYSTEM = (
        "You convert a focus-timer command into one line.\n"
        "Reply with ONLY: ACTION=<start|stop|pause|resume|status|add|help> MINUTES=<number|none>\n"
        "Examples:\n"
        "make 20 min -> ACTION=start MINUTES=20\n"
        "kick it off -> ACTION=start MINUTES=none\n"
        "give me 15 more minutes -> ACTION=add MINUTES=15\n"
        "how am i doing -> ACTION=status MINUTES=none\n"
        "take a break -> ACTION=pause MINUTES=none\n"
        "ok back to it -> ACTION=resume MINUTES=none\n"
        "i'm finished -> ACTION=stop MINUTES=none\n"
    )

    def __init__(self):
        self.llm = None
        self.available = False
        self.reason = ""
        try:
            from llama_cpp import Llama
        except ImportError:
            self.reason = "llama-cpp-python not installed"
            return
        import os
        if not os.path.exists(MODEL_PATH):
            self.reason = f"model file not found at {MODEL_PATH}"
            return
        try:
            self.llm = Llama(
                model_path=MODEL_PATH,
                n_ctx=LLM_CTX,
                n_threads=LLM_THREADS,
                use_mmap=True,      # read weights from disk -> lower resident RAM
                verbose=False,
            )
            self.available = True
        except Exception as e:                       # noqa: BLE001 - report, don't crash
            self.reason = f"failed to load model: {e}"

    def parse(self, text):
        if not self.available:
            return None
        prompt = (
            f"<|im_start|>system\n{self.SYSTEM}<|im_end|>\n"
            f"<|im_start|>user\n{text}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        try:
            out = self.llm(prompt, max_tokens=LLM_MAX_TOK, temperature=0.0,
                           stop=["<|im_end|>", "\n"])
            reply = out["choices"][0]["text"]
        except Exception:                            # noqa: BLE001
            return None
        return self._read(reply)

    @staticmethod
    def _read(reply):
        a = re.search(r"ACTION=([a-z]+)", reply, re.I)
        m = re.search(r"MINUTES=(\d+)", reply, re.I)
        valid = {"start", "stop", "pause", "resume", "status", "add", "help"}
        if not a or a.group(1).lower() not in valid:
            return Intent("unknown", None, "llm")
        minutes = int(m.group(1)) if m else None
        return Intent(a.group(1).lower(), minutes, "llm")


# =============================================================================
#  parse() - the hybrid: rules first, LLM only when rules are unsure
# =============================================================================
def parse(text, llm=None):
    intent = rule_parse(text)
    if intent.action != "unknown":
        return intent                      # rules handled it -> no LLM, no RAM used
    if llm is not None:                     # rules unsure -> ask the tiny model
        guess = llm.parse(text)
        if guess is not None and guess.action != "unknown":
            return guess
    return intent                          # still unknown -> friendly fallback later


# =============================================================================
#  dispatch() - apply an intent to the session and return a human reply
# =============================================================================
def _fmt(seconds):
    """Seconds -> 'H:MM:SS' or 'MM:SS'."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def dispatch(intent, session):
    a = intent.action

    if a == "start":
        session.start(intent.minutes)
        if session.target_sec:
            return f"Session started - goal {intent.minutes} min ({_fmt(session.target_sec)} on the clock)."
        return "Session started - counting up. Say 'how long' anytime."

    if a == "add":
        if session.state == "IDLE":
            session.start(intent.minutes or DEFAULT_MINUTES)
            return f"No session was running - started a {intent.minutes or DEFAULT_MINUTES} min one."
        session.add_minutes(intent.minutes or 0)
        extra = intent.minutes or 0
        if session.target_sec:
            return f"Added {extra} min. {_fmt(session.remaining())} left of {_fmt(session.target_sec)}."
        return f"Added {extra} min as a goal. {_fmt(session.remaining())} left."

    if a == "status":
        if session.state == "IDLE":
            return "No session running. Say 'start 20 min' to begin."
        worked = _fmt(session.elapsed())
        if session.target_sec:
            return f"You've worked {worked}, {_fmt(session.remaining())} left of {_fmt(session.target_sec)}."
        return f"You've worked {worked} so far."

    if a == "pause":
        return "Paused." if session.pause() else "Nothing to pause."

    if a == "resume":
        return "Resumed." if session.resume() else "Nothing to resume."

    if a == "stop":
        if session.state == "IDLE":
            return "No session was running."
        total = session.stop()
        return f"Session ended. Total worked: {_fmt(total)}."

    if a == "help":
        return HELP_TEXT

    if a == "quit":
        return "__QUIT__"

    # unknown
    return "I didn't catch that. Try: 'start 20 min', 'how long', 'add 15 min', 'pause', 'stop', or 'help'."


HELP_TEXT = (
    "Commands (say them naturally - phrasing is flexible):\n"
    "  start 20 min / make 20 minutes  -> begin a session with a goal\n"
    "  how long have i worked          -> report elapsed (and time left)\n"
    "  add 15 minutes                  -> extend the goal\n"
    "  pause / resume                  -> freeze / continue\n"
    "  stop                            -> end the session, report total\n"
    "  help                            -> this list\n"
    "  exit                            -> quit the program"
)


# =============================================================================
#  REPL + self-test
# =============================================================================
def _maybe_announce_end(session):
    """Print the 'goal reached' cue once, the text stand-in for the buzzer/BITTI."""
    if session.state == "RUNNING" and session.is_finished() and not session._announced_end:
        session._announced_end = True
        print(f"  *** Goal reached - you've worked {_fmt(session.target_sec)}! (BITTI) ***")


def run_repl(use_llm):
    session = Session()
    llm = None
    if use_llm:
        print("Loading local AI model (SmolLM2-135M)...")
        llm = LlmParser()
        if llm.available:
            print("Local AI ready - flexible phrasing enabled.\n")
        else:
            print(f"Local AI unavailable ({llm.reason}); using rule-based parsing only.\n")
            llm = None

    print("Exact Hour - text assistant. Type a command, or 'help'. ('exit' to quit.)\n")
    while True:
        _maybe_announce_end(session)
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return
        if not text:
            continue
        reply = dispatch(parse(text, llm), session)
        if reply == "__QUIT__":
            print("Bye.")
            return
        print(reply)


# A fixed transcript so you can confirm the pipeline works without typing.
SELFTEST = [
    "make 20 min",
    "how long have i worked",
    "add 15 minutes",
    "pause",
    "resume",
    "how am i doing",
    "asdf gibberish",
    "stop",
    "kick off a new 5 minute session",
    "stop",
]


def run_selftest():
    session = Session()
    print("=== self-test (rule-based parser, no model needed) ===\n")
    for line in SELFTEST:
        intent = parse(line, llm=None)
        reply = dispatch(intent, session)
        print(f"> {line}")
        print(f"   [{intent.action}{'' if intent.minutes is None else ' '+str(intent.minutes)}] {reply}\n")
    print("=== self-test done ===")


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        run_selftest()
    else:
        run_repl(use_llm=("--llm" in args))


if __name__ == "__main__":
    main()
