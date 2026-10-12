"""Single-origin local HTTP server for the portable Windows package.

Use a dedicated stdlib web server instead of shipping nginx or Node to testers.
Runs alongside Uvicorn and forwards API calls without changing app routes.
"""
from __future__ import annotations

import http.client
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent / "www"
API_HOST, API_PORT = "127.0.0.1", 18001
MAX_BODY = 30 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def _handle(self):
        path = urlsplit(self.path).path
        if path == "/api" or path.startswith("/api/"):
            self._proxy()
            return
        target = (ROOT / path.lstrip("/")).resolve()
        if not target.is_relative_to(ROOT.resolve()):
            self.send_error(403)
            return
        if not target.is_file():
            # Client-side routes must resolve to the React index.
            target = ROOT / "index.html"
        if not target.is_file():
            self.send_error(503, "Frontend build ontbreekt")
            return
        payload = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store" if target.name == "version.json" else "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _proxy(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > MAX_BODY:
                self.send_error(413)
                return
            data = self.rfile.read(size) if size else None
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in {"host", "connection", "content-length", "transfer-encoding"}}
            headers["Host"] = f"{API_HOST}:{API_PORT}"
            connection = http.client.HTTPConnection(API_HOST, API_PORT, timeout=300)
            connection.request(self.command, self.path, body=data, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for k, v in response.getheaders():
                if k.lower() not in {"connection", "transfer-encoding", "content-length", "keep-alive"}:
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
            connection.close()
        except (OSError, http.client.HTTPException) as exc:
            self.send_error(502, f"Backend niet beschikbaar: {type(exc).__name__}")

    def do_GET(self): self._handle()
    def do_HEAD(self): self._handle()
    def do_POST(self): self._handle()
    def do_PUT(self): self._handle()
    def do_PATCH(self): self._handle()
    def do_DELETE(self): self._handle()


if __name__ == "__main__":
    if not ROOT.is_dir():
        raise SystemExit("Frontend-bestanden ontbreken: " + str(ROOT))
    port = int(os.getenv("INHUIS_PORT", "5174"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
