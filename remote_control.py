#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Local-Network Remote Control  (remote_control.py)
# -----------------------------------------------------------------------------
#  This module lets the Exact Hour clock be controlled from another device on
#  the SAME Wi-Fi network (e.g. the Android app) over plain HTTP + JSON.
#
#  THE GOLDEN RULE - THREAD SAFETY:
#    The timer and the MAX7219 display are touched by EXACTLY ONE thread: the
#    main loop in main.py. The HTTP server runs in its OWN background thread, so
#    it must NEVER call timer/display methods directly (two threads drawing to
#    the same SPI bus would corrupt the display).
#
#    Instead the flow is:
#       HTTP thread  --enqueues a Command-->  CommandBus  --drained by-->  main loop
#       main loop    --applies it to the timer, then publishes a status snapshot
#       HTTP thread  --reads the snapshot-->  replies with JSON
#
#    So the HTTP side only ever (a) puts Commands on a queue and (b) reads an
#    immutable status snapshot. All real work stays on the main thread.
#
#  This file has ZERO hardware dependencies (only the Python standard library),
#  which means it can be unit-tested on a normal PC - see test_remote_control.py.
# =============================================================================

import json
import os
import queue
import socket
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Largest POST body we will read. Our requests are a few bytes ({"delta": 5});
# this just stops a misbehaving/hostile client from making us block on a huge
# (or never-arriving) Content-Length.
MAX_BODY_SIZE = 64 * 1024


# =============================================================================
#  _QuietThreadingHTTPServer - same server, minus the harmless-disconnect noise
# -----------------------------------------------------------------------------
#  The Android app polls /api/status repeatedly and closes old keep-alive
#  connections as it goes. When a client drops a socket, socketserver raises
#  ConnectionResetError / BrokenPipeError from DEEP inside its own request loop
#  (handle_one_request -> rfile.readline), BEFORE our do_GET/do_POST handlers
#  run - so our per-request try/except can't catch it, and the default
#  handle_error() prints a full traceback for every disconnect. That is pure
#  cosmetic noise (nothing actually failed), so we swallow exactly those
#  expected disconnect errors here and let any genuinely unexpected error
#  through to the normal handler.
# =============================================================================
class _QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                            ConnectionAbortedError)):
            return                       # client hung up - expected, ignore
        super().handle_error(request, client_address)


# =============================================================================
#  Command - one instruction travelling from the HTTP thread to the main loop
# -----------------------------------------------------------------------------
#  `done` is set by the main loop once the command has been applied, and
#  `result` then holds the fresh status snapshot. The HTTP thread waits briefly
#  on `done` so it can reply with the UP-TO-DATE state (snappy UI feedback).
# =============================================================================
class Command:
    def __init__(self, action, value=None):
        self.action = action          # "toggle" | "start" | "pause" | ...
        self.value  = value           # int (adjust) or dict (set) or None
        self.done   = threading.Event()
        self.result = None            # status dict, filled in by the main loop


# =============================================================================
#  RemoteControl - the thread-safe bridge
# =============================================================================
class RemoteControl:
    def __init__(self):
        self._queue       = queue.Queue()
        self._lock        = threading.Lock()
        self._snapshot    = {}
        self._httpd       = None
        self._http_thread = None

    # ----- called by the HTTP thread -----------------------------------------

    def submit(self, action, value=None, timeout=1.0):
        """Queue a command, wait briefly for the main loop to apply it, and
        return the resulting status snapshot. If the main loop is busy/stopped,
        fall back to the last known snapshot after `timeout` seconds."""
        cmd = Command(action, value)
        self._queue.put(cmd)
        cmd.done.wait(timeout)
        return cmd.result if cmd.result is not None else self.snapshot()

    def snapshot(self):
        """Return the most recently published status snapshot.

        We return the stored dict directly (no copy): every dict that reaches
        publish() comes from a fresh timer.status_dict() and is never mutated
        afterwards, and the HTTP side only reads it (json.dumps). The lock makes
        the reference read/write atomic, which is all we need."""
        with self._lock:
            return self._snapshot

    # ----- called by the main (timer) loop -----------------------------------

    def publish(self, status):
        """Main loop calls this every iteration with the timer's current state.
        `status` must be a freshly built dict the caller will not mutate again
        (status_dict() returns a new dict each call), so storing it directly is
        safe and avoids a dict copy on every loop iteration."""
        with self._lock:
            self._snapshot = status

    def drain(self):
        """Return (and remove) every command currently waiting in the queue."""
        cmds = []
        while True:
            try:
                cmds.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return cmds

    # ----- server lifecycle ---------------------------------------------------

    def start_server(self, host="0.0.0.0", port=8080):
        """Start the HTTP server in a daemon thread. Returns the server object."""
        control = self
        index = _load_index()        # optional built-in web remote (web_remote.html)
        self._httpd = _QuietThreadingHTTPServer((host, port), _make_handler(control, index))
        self._http_thread = threading.Thread(target=self._httpd.serve_forever,
                                             name="exact-hour-http", daemon=True)
        self._http_thread.start()
        return self._httpd

    def stop_server(self):
        if self._httpd is None:
            return
        # shutdown() blocks until serve_forever() returns, so it must NOT be
        # called from the HTTP thread itself (that would deadlock). Guard against
        # a future caller accidentally doing so from inside a request handler.
        if threading.current_thread() is self._http_thread:
            raise RuntimeError("stop_server() must be called from the main thread, "
                               "not the HTTP handler thread (would deadlock).")
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._http_thread = None


# =============================================================================
#  apply_command - run a Command against a timer object (main thread only)
# -----------------------------------------------------------------------------
#  The timer object only needs these methods:
#     cmd_toggle(), cmd_start(), cmd_pause(), cmd_resume(), cmd_reset(),
#     cmd_adjust(delta_minutes), cmd_set(minutes, seconds), status_dict()
#  Both main.py's ExactHour and the test's FakeTimer implement them, so this
#  one function drives both.
# =============================================================================
def apply_command(timer, cmd):
    a = cmd.action
    if a == "toggle":
        timer.cmd_toggle()
    elif a == "start":
        timer.cmd_start()
    elif a == "pause":
        timer.cmd_pause()
    elif a == "resume":
        timer.cmd_resume()
    elif a == "reset":
        timer.cmd_reset()
    elif a == "adjust":
        timer.cmd_adjust(int(cmd.value or 0))
    elif a == "set":
        v = cmd.value or {}
        timer.cmd_set(int(v.get("minutes", 0)), int(v.get("seconds", 0)))
    # unknown actions are silently ignored - the route table below never sends one


def pump(timer, control):
    """Drain queued commands, apply each on THIS (main) thread, hand the fresh
    status back to the waiting HTTP request, then publish the latest snapshot.
    Call this once per iteration of the main loop."""
    for cmd in control.drain():
        try:
            apply_command(timer, cmd)
            cmd.result = timer.status_dict()
        except Exception:                 # never let a bad request crash the loop
            # Keep the clock running, but don't swallow the cause silently -
            # log it to stderr so a real bug is at least visible in the journal.
            traceback.print_exc(file=sys.stderr)
            cmd.result = timer.status_dict()
        finally:
            cmd.done.set()
    control.publish(timer.status_dict())


# =============================================================================
#  HTTP routing
# -----------------------------------------------------------------------------
#  GET  /api/status            -> current status snapshot
#  POST /api/toggle            -> START button behaviour (start/pause/resume/new)
#  POST /api/start             -> start the countdown (if idle)
#  POST /api/pause             -> pause (if running)
#  POST /api/resume            -> resume (if paused)
#  POST /api/reset             -> reset to the default idle time
#  POST /api/adjust  {delta}   -> add `delta` minutes (idle/paused only)
#  POST /api/set     {minutes,seconds} -> set an absolute time (idle/paused only)
#
#  Every response is JSON. CORS headers are included so a browser/PWA could also
#  talk to the clock; they are harmless for the native app.
# =============================================================================
_POST_ROUTES = {
    "/api/toggle": "toggle",
    "/api/start":  "start",
    "/api/pause":  "pause",
    "/api/resume": "resume",
    "/api/reset":  "reset",
    "/api/adjust": "adjust",
    "/api/set":    "set",
}


def _load_index():
    """Read the optional built-in web remote (web_remote.html) that sits next to
    this module, so the clock can serve a control page at GET /. Returns the
    bytes, or None if the file isn't there (then / just returns JSON status)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_remote.html")
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _make_handler(control, index_html=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # ---- helpers --------------------------------------------------------
        def _send(self, code, payload):
            try:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass        # client hung up mid-response; nothing we can do

        def _send_html(self, body):
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass

        def _read_json(self):
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
            except ValueError:
                return {}
            # Ignore non-positive or oversized bodies (a bogus huge Content-Length
            # would otherwise block self.rfile.read waiting for bytes that never come).
            if length <= 0 or length > MAX_BODY_SIZE:
                return {}
            try:
                raw = self.rfile.read(length)
            except OSError:
                return {}       # client disconnected mid-body
            try:
                data = json.loads(raw or b"{}")
                return data if isinstance(data, dict) else {}
            except (ValueError, TypeError):
                return {}

        def _path(self):
            return self.path.split("?", 1)[0].rstrip("/") or "/"

        # ---- verbs ----------------------------------------------------------
        #  Each verb is wrapped so a malformed request or a dropped connection
        #  only ends that one request - it never tears down the handler thread.
        def do_GET(self):
            try:
                path = self._path()
                if path == "/" and index_html is not None:
                    self._send_html(index_html)            # built-in web remote page
                elif path in ("/api/status", "/api", "/"):
                    self._send(200, control.snapshot())    # JSON status snapshot
                else:
                    self._send(404, {"error": "not found"})
            except Exception:
                traceback.print_exc(file=sys.stderr)

        def do_POST(self):
            try:
                action = _POST_ROUTES.get(self._path())
                if action is None:
                    self._send(404, {"error": "not found"})
                    return

                value = None
                if action == "adjust":
                    try:
                        value = int(self._read_json().get("delta", 0))
                    except (TypeError, ValueError):
                        value = 0
                elif action == "set":
                    body = self._read_json()
                    try:
                        value = {"minutes": int(body.get("minutes", 0)),
                                 "seconds": int(body.get("seconds", 0))}
                    except (TypeError, ValueError):
                        value = {"minutes": 0, "seconds": 0}

                self._send(200, control.submit(action, value))
            except Exception:
                traceback.print_exc(file=sys.stderr)

        def do_OPTIONS(self):
            try:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Content-Length", "0")
                self.end_headers()
            except OSError:
                pass

        def log_message(self, *args):
            pass        # keep the console quiet (no per-request logging)

    return Handler


# =============================================================================
#  local_ip - best-effort "what IP should I type into the app?"
# =============================================================================
def local_ip():
    """Return the LAN IP of this machine (the address the app connects to).
    Uses the standard 'connect a UDP socket' trick - no packets are sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
