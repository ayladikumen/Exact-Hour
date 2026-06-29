#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Voice Listener (Pi side)  (voice/listener.py)
# -----------------------------------------------------------------------------
#  Runs ON THE PI. Captures a short burst of speech from the microphone, turns
#  it into text with Vosk (offline, ~50 MB model, no internet, no API key), and
#  POSTs that text to the PC "brain" (pc_brain/brain_server.py) which does the
#  AI + action. NO AI runs here - this is ears + mouth-to-text only.
#
#  THREADING (mirrors remote_control.py's model so main.py stays simple):
#    The MAX7219 display + the GPIO buttons are owned by main.py's ONE main
#    loop. Speech recognition is slow and blocking, so it must NOT run on that
#    loop or the clock would freeze. Instead:
#
#       main loop  --double-press START--> request_listen()  (just sets an Event)
#       listener thread  --wakes, records, runs Vosk, POSTs text to the PC-->
#
#    The main loop never blocks; it only flips a flag. Everything heavy happens
#    on this daemon thread.
#
#  DEPENDENCIES are imported LAZILY inside start()/_listen_once() so that:
#    * main.py can `import voice` and still run as a plain timer if vosk/
#      sounddevice aren't installed (the guard in main.py handles ImportError).
#    * the pure helpers below (post_command) stay unit-testable on any PC.
#
#  Install on the Pi:   pip install vosk sounddevice   (+ a USB mic, see README)
# =============================================================================

import json
import os
import sys
import threading
import urllib.request
import urllib.error


# =============================================================================
#  post_command - send recognized text to the PC brain (stdlib only, testable)
# =============================================================================
def post_command(brain_url, text, timeout=8.0):
    """POST {"text": ...} to the brain's /command endpoint. Returns the decoded
    JSON reply dict, or {"ok": False, "error": ...} on any failure (never raises)."""
    url = brain_url.rstrip("/") + "/command"
    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        return {"ok": False, "error": str(exc)}


# =============================================================================
#  VoiceListener
# =============================================================================
class VoiceListener:
    def __init__(self, brain_url, model_path="voice/models/vosk-model-small-en-us-0.15",
                 sample_rate=16000, max_seconds=6.0, on_result=None):
        """
        brain_url   : base URL of the PC brain, e.g. "http://192.168.1.20:8090"
        model_path  : folder of the unpacked Vosk model (see setup_voice.sh)
        sample_rate : 16 kHz suits the small Vosk models
        max_seconds : hard cap on one listen window (we also stop early on silence)
        on_result   : optional callback(text, reply_dict) for UI feedback/logging
        """
        self.brain_url   = brain_url
        self.model_path  = model_path
        self.sample_rate = sample_rate
        self.max_seconds = max_seconds
        self.on_result   = on_result

        self._wake     = threading.Event()    # set by request_listen()
        self._stop     = threading.Event()    # set by stop()
        self._busy     = threading.Event()    # set while a listen is in progress
        self._thread   = None
        self._model    = None                 # loaded once, lazily, on start()
        self.available = False                 # True once deps + model are ready

    # ----- called by the main loop (cheap, non-blocking) ---------------------

    def request_listen(self):
        """Ask the listener to capture one command. No-op if it's already busy
        or not available. Returns True if a listen was scheduled."""
        if not self.available or self._busy.is_set():
            return False
        self._wake.set()
        return True

    # ----- lifecycle ----------------------------------------------------------

    def start(self):
        """Load the Vosk model and start the background thread. On any failure
        (missing deps/model) it logs and stays unavailable - main.py keeps
        running as a plain timer."""
        try:
            from vosk import Model            # noqa: F401  (import = availability probe)
            import sounddevice                 # noqa: F401
        except ImportError as exc:
            print(f"[voice] disabled - missing dependency: {exc} "
                  f"(pip install vosk sounddevice)", file=sys.stderr)
            return False

        if not os.path.isdir(self.model_path):
            print(f"[voice] disabled - Vosk model not found at {self.model_path} "
                  f"(run voice/setup_voice.sh)", file=sys.stderr)
            return False

        try:
            from vosk import Model
            self._model = Model(self.model_path)
        except Exception as exc:               # noqa: BLE001 - report, don't crash
            print(f"[voice] disabled - could not load model: {exc}", file=sys.stderr)
            return False

        self.available = True
        self._thread = threading.Thread(target=self._run, name="exact-hour-voice",
                                        daemon=True)
        self._thread.start()
        print(f"[voice] ready - double-press START to speak; commands go to "
              f"{self.brain_url}")
        return True

    def stop(self):
        self._stop.set()
        self._wake.set()                       # unblock the thread so it can exit

    # ----- the background thread ----------------------------------------------

    def _run(self):
        while not self._stop.is_set():
            self._wake.wait()                  # sleep until a double-press wakes us
            self._wake.clear()
            if self._stop.is_set():
                break
            self._busy.set()
            try:
                self._listen_once()
            except Exception:                  # noqa: BLE001 - never kill the thread
                import traceback
                traceback.print_exc(file=sys.stderr)
            finally:
                self._busy.clear()

    def _listen_once(self):
        """Record one utterance and ship the recognized text to the brain."""
        import time
        import sounddevice as sd
        from vosk import KaldiRecognizer

        rec = KaldiRecognizer(self._model, self.sample_rate)
        print("[voice] listening...")

        # blocksize 0 = let the driver pick; int16 mono is what Vosk expects.
        with sd.RawInputStream(samplerate=self.sample_rate, blocksize=8000,
                               dtype="int16", channels=1) as stream:
            started = time.monotonic()
            while time.monotonic() - started < self.max_seconds:
                data, _overflow = stream.read(4000)
                if rec.AcceptWaveform(bytes(data)):
                    break                      # Vosk detected end-of-utterance (silence)

        text = (json.loads(rec.FinalResult()).get("text") or "").strip()
        if not text:
            print("[voice] (heard nothing)")
            if self.on_result:
                self.on_result("", {"ok": False, "error": "no speech"})
            return

        print(f"[voice] heard: {text!r} -> sending to brain")
        reply = post_command(self.brain_url, text)
        msg = reply.get("result", {}).get("reply") or reply.get("error") or reply
        print(f"[voice] brain: {msg}")
        if self.on_result:
            self.on_result(text, reply)
