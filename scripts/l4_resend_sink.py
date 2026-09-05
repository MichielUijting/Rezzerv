from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

_lock = threading.Lock()
_latest: dict[str, object] | None = None
_counter = 0


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/latest":
            with _lock:
                payload = dict(_latest) if _latest is not None else None
            if payload is None:
                self._json(404, {"detail": "no email captured"})
                return
            self._json(200, payload)
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        global _latest, _counter
        if self.path != "/emails":
            self._json(404, {"detail": "not found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._json(400, {"detail": "invalid json"})
            return
        with _lock:
            _latest = dict(payload)
            _counter += 1
            message_id = f"l4-resend-{_counter}"
        self._json(200, {"id": message_id})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"resend-sink: {fmt % args}", flush=True)


if __name__ == "__main__":
    print("L4_RESEND_SINK_READY port=8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
