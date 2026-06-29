#!/usr/bin/env python3
# =============================================================================
#  Exact Hour - Brain HTTP server  (pc_brain/brain_server.py)
# -----------------------------------------------------------------------------
#  Runs on the main PC (the Ollama host). Exposes ONE endpoint the Pi posts
#  recognized speech to:
#
#     POST /command   {"text": "turn on the light"}
#        -> {"text", "intent": {...}, "result": {"ok", "reply", ...}}
#
#  It also serves GET /health for a quick "is it up?" check. The heavy lifting
#  (understand + act) is in brain.py / router.py; this file is just the socket.
#
#  Stdlib only (http.server + urllib via the backends). Start it with:
#     py pc_brain/brain_server.py
#  Configure via config.json (see config.example.json).
# =============================================================================

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config as cfg_mod
from brain import Brain

MAX_BODY_SIZE = 64 * 1024


def build_brain(cfg):
    """Construct the Brain from config: one backend per domain, plus the
    optional Ollama client. Missing-backend errors are surfaced loudly here."""
    backends = {}
    for domain, name in cfg["backends"].items():
        backends[domain] = cfg_mod.make_backend(name, cfg)

    llm = None
    if cfg.get("use_llm"):
        from ollama_client import OllamaClient
        llm = OllamaClient(base_url=cfg["ollama_url"], model=cfg["ollama_model"])

    return Brain(backends, llm=llm)


def _make_handler(brain):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code, payload):
            try:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
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
            if length <= 0 or length > MAX_BODY_SIZE:
                return {}
            try:
                raw = self.rfile.read(length)
                data = json.loads(raw or b"{}")
                return data if isinstance(data, dict) else {}
            except (OSError, ValueError, TypeError):
                return {}

        def _path(self):
            return self.path.split("?", 1)[0].rstrip("/") or "/"

        def do_GET(self):
            try:
                if self._path() in ("/health", "/"):
                    self._send(200, {"ok": True, "name": "Exact Hour brain"})
                else:
                    self._send(404, {"ok": False, "error": "not found"})
            except Exception:
                traceback.print_exc(file=sys.stderr)

        def do_POST(self):
            try:
                if self._path() != "/command":
                    self._send(404, {"ok": False, "error": "not found"})
                    return
                text = str(self._read_json().get("text", "")).strip()
                if not text:
                    self._send(400, {"ok": False, "error": "missing 'text'"})
                    return
                out = brain.handle(text)
                # Echo a one-line summary to the console so you can watch it work.
                print(f"  heard: {text!r}\n   -> {out['intent']}\n   -> "
                      f"{out['result'].get('reply')}")
                self._send(200, out)
            except Exception:
                traceback.print_exc(file=sys.stderr)
                self._send(500, {"ok": False, "error": "internal error"})

        def log_message(self, *args):
            pass        # quiet per-request logging; we print our own summary

    return Handler


def main():
    cfg = cfg_mod.load()
    brain = build_brain(cfg)

    httpd = ThreadingHTTPServer((cfg["host"], cfg["port"]), _make_handler(brain))
    print("Exact Hour brain listening on http://{}:{}/command".format(
        cfg["host"], cfg["port"]))
    print("  backends: {}   llm: {}".format(
        cfg["backends"], cfg["ollama_model"] if cfg.get("use_llm") else "off"))
    print("  POST {\"text\": \"turn on the light\"} to /command")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
