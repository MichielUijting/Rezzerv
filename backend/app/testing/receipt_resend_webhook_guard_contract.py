from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.receipt_resend_webhook_guard import install_receipt_resend_webhook_guard

SECRET_BYTES = b"rezzerv-resend-webhook-contract-secret"
SECRET = "whsec_" + base64.b64encode(SECRET_BYTES).decode("ascii")


def signature(body: bytes, svix_id: str, timestamp: int) -> str:
    signed = f"{svix_id}.{timestamp}.".encode("utf-8") + body
    digest = base64.b64encode(hmac.new(SECRET_BYTES, signed, hashlib.sha256).digest()).decode("ascii")
    return f"v1,{digest}"


def headers(body: bytes, svix_id: str, timestamp: int | None = None) -> dict[str, str]:
    current = int(time.time() if timestamp is None else timestamp)
    return {
        "svix-id": svix_id,
        "svix-timestamp": str(current),
        "svix-signature": signature(body, svix_id, current),
        "content-type": "application/json",
    }


def build_app():
    app = FastAPI()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    state = {"calls": 0, "fail_once": True}

    @app.post("/api/receipts/inbound")
    async def inbound(request: Request):
        state["calls"] += 1
        payload = await request.json()
        if payload.get("force_server_error") and state["fail_once"]:
            state["fail_once"] = False
            return JSONResponse(status_code=500, content={"detail": "temporary"})
        return {"accepted": True, "payload": payload}

    @app.post("/api/other")
    async def other():
        return {"ok": True}

    module = SimpleNamespace(app=app, engine=engine, text=text)
    install_receipt_resend_webhook_guard(module)
    return app, engine, state


def main() -> None:
    previous = os.environ.get("REZZERV_RESEND_WEBHOOK_SECRET")
    try:
        os.environ.pop("REZZERV_RESEND_WEBHOOK_SECRET", None)
        app, engine, state = build_app()
        client = TestClient(app)

        payload = {"type": "email.received", "data": {"to": ["bon+household-a@example.test"]}}
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        response = client.post("/api/receipts/inbound", content=body)
        assert response.status_code == 503, response.text
        assert state["calls"] == 0

        os.environ["REZZERV_RESEND_WEBHOOK_SECRET"] = SECRET
        response = client.post("/api/receipts/inbound", content=body)
        assert response.status_code == 400, response.text
        assert state["calls"] == 0

        bad_headers = headers(body, "evt-bad-signature")
        bad_headers["svix-signature"] = "v1,invalid"
        response = client.post("/api/receipts/inbound", content=body, headers=bad_headers)
        assert response.status_code == 401, response.text
        assert state["calls"] == 0

        stale = int(time.time()) - 600
        response = client.post("/api/receipts/inbound", content=body, headers=headers(body, "evt-stale", stale))
        assert response.status_code == 401, response.text
        assert state["calls"] == 0

        valid_headers = headers(body, "evt-valid")
        response = client.post("/api/receipts/inbound", content=body, headers=valid_headers)
        assert response.status_code == 200, response.text
        assert response.json()["accepted"] is True
        assert state["calls"] == 1

        response = client.post("/api/receipts/inbound", content=body, headers=valid_headers)
        assert response.status_code == 409, response.text
        assert state["calls"] == 1

        with engine.begin() as conn:
            stored = conn.execute(text("SELECT status, payload_sha256 FROM receipt_webhook_deliveries WHERE svix_id = 'evt-valid'")).mappings().first()
        assert stored and stored["status"] == "completed"
        assert stored["payload_sha256"] == hashlib.sha256(body).hexdigest()

        retry_payload = {"type": "email.received", "force_server_error": True}
        retry_body = json.dumps(retry_payload, separators=(",", ":")).encode("utf-8")
        retry_headers = headers(retry_body, "evt-retry")
        response = client.post("/api/receipts/inbound", content=retry_body, headers=retry_headers)
        assert response.status_code == 500, response.text
        with engine.begin() as conn:
            retry_row = conn.execute(text("SELECT svix_id FROM receipt_webhook_deliveries WHERE svix_id = 'evt-retry'")).first()
        assert retry_row is None

        response = client.post("/api/receipts/inbound", content=retry_body, headers=retry_headers)
        assert response.status_code == 200, response.text
        assert state["calls"] == 3

        response = client.post("/api/other")
        assert response.status_code == 200, response.text

        print("RECEIPT_RESEND_WEBHOOK_GUARD_GREEN")
    finally:
        if previous is None:
            os.environ.pop("REZZERV_RESEND_WEBHOOK_SECRET", None)
        else:
            os.environ["REZZERV_RESEND_WEBHOOK_SECRET"] = previous


if __name__ == "__main__":
    main()
