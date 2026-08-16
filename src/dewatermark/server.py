"""Local web UI server — stdlib only, zero dependencies.

Run with: dewatermark --serve [--port 8373]

Serves the bundled single-file UI plus two local API endpoints the
GitHub Pages version cannot offer:

  GET  /api/health    -> {"local": true, "ollama": bool, "models": [...]}
  POST /api/rewrite   -> {"text": ..., "model": ...} -> {"text", "backend"}
  POST /api/translate -> {"text": ...} -> {"text", "route", "backend"}

Everything runs on 127.0.0.1. Nothing leaves the machine except the
optional MyMemory translation fallback (argos local preferred).
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import scrub_text
from .rewrite import DEFAULT_MODEL, rewrite
from .translate import round_trip

STATIC_DIR = Path(__file__).parent / "static"
OLLAMA_URL = "http://localhost:11434"


def ollama_health() -> dict:
    out = {"ollama": False, "models": []}
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
        out["ollama"] = True
        out["models"] = [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "dewatermark/0.1"

    def log_message(self, format, *args):  # noqa: A002 quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        if self.path == "/":
            index = STATIC_DIR / "index.html"
            if not index.exists():
                # repo checkout fallback
                repo_docs = Path(__file__).parents[2] / "docs" / "index.html"
                index = repo_docs if repo_docs.exists() else index
            try:
                body = index.read_bytes()
                self._send(200, body, "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(404, b"UI file not found", "text/plain")
            return
        if self.path == "/api/health":
            h = ollama_health()
            h["local"] = True
            h["default_model"] = DEFAULT_MODEL
            self._json(200, h)
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            self._json(400, {"error": "bad json"})
            return

        if self.path == "/api/rewrite":
            text = payload.get("text", "")
            model = payload.get("model") or DEFAULT_MODEL
            if not text.strip():
                self._json(400, {"error": "empty text"})
                return
            try:
                cleaned, _ = scrub_text(text)
                rewritten, backend = rewrite(cleaned, model=model)
                self._json(200, {"text": rewritten, "backend": backend})
            except Exception as e:
                self._json(500, {"error": str(e)})
            return

        if self.path == "/api/translate":
            text = payload.get("text", "")
            if not text.strip():
                self._json(400, {"error": "empty text"})
                return
            try:
                cleaned, _ = scrub_text(text)
                out, rep = round_trip(cleaned)
                self._json(200, {"text": out, **rep})
            except Exception as e:
                self._json(500, {"error": str(e)})
            return

        self._json(404, {"error": "not found"})


def serve(port: int = 8373, open_browser: bool = True):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"dewatermark local UI: {url}")
    print("  Ctrl-C to stop. Everything runs on 127.0.0.1.")
    h = ollama_health()
    print(
        f"  Ollama: {'UP' if h['ollama'] else 'DOWN (deep rewrite unavailable)'}"
    )
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
