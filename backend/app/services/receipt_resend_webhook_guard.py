from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any

from fastapi import HTTPException, Request

INBOUND_PATH = "/api/receipts/inbound"
MAX_TIMESTAMP_SKEW_SECONDS = 300


def _webhook_secret() -> str:
    return str(os.getenv("REZZERV_RESEND_WEBHOOK_SECRET", "") or "").strip()


def _decode_secret(secret: str) -> bytes:
    encoded = secret[6:] if secret.startswith("whsec_") else secret
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="De Resend webhooksecret is ongeldig geconfigureerd.") from exc


def _signature_candidates(value: str) -> list[str]:
    candidates: list[str] = []
    for part in str(value or "").split():
        version, separator, signature = part.partition(",")
        if separator and version == "v1" and signature:
            candidates.append(signature)
    return candidates


def verify_resend_webhook(*, body: bytes, svix_id: str, svix_timestamp: str, svix_signature: str, now: int | None = None) -> None:
    secret = _webhook_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="De Resend webhooksecret is niet geconfigureerd.")
    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(status_code=400, detail="Verplichte Resend webhookheaders ontbreken.")
    try:
        timestamp = int(svix_timestamp)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="De Resend webhooktimestamp is ongeldig.") from exc
    current = int(time.time() if now is None else now)
    if abs(current - timestamp) > MAX_TIMESTAMP_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="De Resend webhooktimestamp valt buiten het toegestane tijdvenster.")

    signed_payload = f"{svix_id}.{svix_timestamp}.".encode("utf-8") + body
    expected = base64.b64encode(hmac.new(_decode_secret(secret), signed_payload, hashlib.sha256).digest()).decode("ascii")
    candidates = _signature_candidates(svix_signature)
    if not candidates or not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise HTTPException(status_code=401, detail="De Resend webhookhandtekening is ongeldig.")


def ensure_delivery_table(module: Any) -> None:
    with module.engine.begin() as conn:
        conn.execute(
            module.text(
                """
                CREATE TABLE IF NOT EXISTS receipt_webhook_deliveries (
                    svix_id TEXT PRIMARY KEY,
                    svix_timestamp INTEGER NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'processing',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


def reserve_delivery(module: Any, *, svix_id: str, svix_timestamp: str, body: bytes) -> None:
    payload_hash = hashlib.sha256(body).hexdigest()
    try:
        with module.engine.begin() as conn:
            conn.execute(
                module.text(
                    """
                    INSERT INTO receipt_webhook_deliveries (
                        svix_id, svix_timestamp, payload_sha256, status, created_at, updated_at
                    ) VALUES (
                        :svix_id, :svix_timestamp, :payload_sha256, 'processing', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "svix_id": svix_id,
                    "svix_timestamp": int(svix_timestamp),
                    "payload_sha256": payload_hash,
                },
            )
    except Exception as exc:
        message = str(exc).lower()
        if "unique" in message or "primary key" in message:
            raise HTTPException(status_code=409, detail="Deze Resend webhooklevering is al verwerkt.") from exc
        raise


def finalize_delivery(module: Any, *, svix_id: str, status: str) -> None:
    with module.engine.begin() as conn:
        conn.execute(
            module.text(
                """
                UPDATE receipt_webhook_deliveries
                SET status = :status, updated_at = CURRENT_TIMESTAMP
                WHERE svix_id = :svix_id
                """
            ),
            {"svix_id": svix_id, "status": status},
        )


def release_delivery(module: Any, *, svix_id: str) -> None:
    with module.engine.begin() as conn:
        conn.execute(
            module.text("DELETE FROM receipt_webhook_deliveries WHERE svix_id = :svix_id"),
            {"svix_id": svix_id},
        )


def install_receipt_resend_webhook_guard(module: Any) -> None:
    if getattr(module.app.state, "receipt_resend_webhook_guard_installed", False):
        return
    ensure_delivery_table(module)

    @module.app.middleware("http")
    async def receipt_resend_webhook_guard(request: Request, call_next):
        if request.method.upper() != "POST" or request.url.path != INBOUND_PATH:
            return await call_next(request)

        body = await request.body()
        svix_id = str(request.headers.get("svix-id") or "").strip()
        svix_timestamp = str(request.headers.get("svix-timestamp") or "").strip()
        svix_signature = str(request.headers.get("svix-signature") or "").strip()
        verify_resend_webhook(
            body=body,
            svix_id=svix_id,
            svix_timestamp=svix_timestamp,
            svix_signature=svix_signature,
        )
        reserve_delivery(
            module,
            svix_id=svix_id,
            svix_timestamp=svix_timestamp,
            body=body,
        )
        try:
            response = await call_next(request)
        except Exception:
            release_delivery(module, svix_id=svix_id)
            raise
        if int(response.status_code) >= 500:
            release_delivery(module, svix_id=svix_id)
        else:
            finalize_delivery(module, svix_id=svix_id, status="completed")
        return response

    module.app.state.receipt_resend_webhook_guard_installed = True
