"""Durable maintenance-admitted worker for received Lidl and Jumbo receipts.

Pending work can resume after a graceful restart. A crash in the middle of a
receipt leaves its maintenance admission and queue record unresolved: no blind
re-import and no arbitrary lease expiry. Operator reconciliation is required.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path

from cryptography.fernet import InvalidToken
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.integrations.retailer_receipts import RetailerReceiptEnvelope
from app.services.maintenance_postgres_admission import admit_operation, complete_operation
from app.services.maintenance_runtime import _operation
from app.services.maintenance_state_contract import MaintenanceTransitionError
from app.services.platform_feature_flag_service import (
    FEATURE_FLAG_RETAILER_AUTO_IMPORT, is_platform_feature_enabled,
)
from app.services.retailer_account_secure_store import _fernet
from app.services.retailer_receipt_import_service import import_retailer_receipt


LOGGER = logging.getLogger(__name__)
QUEUE_POLL_SECONDS = 5
QUEUE_STARTUP_DELAY_SECONDS = 10


def _claim_one(engine: Engine) -> dict | None:
    """Claim one pending item and commit its durable admission before work."""
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id,household_id,provider,external_receipt_id,
                   payload_sha256,payload_ciphertext
            FROM retailer_import_queue
            WHERE status='pending'
            ORDER BY created_at,id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """)).mappings().first()
        if row is None:
            return None
        # Check again inside the claim transaction; a paused queue retains pending receipts.
        if not is_platform_feature_enabled(conn, FEATURE_FLAG_RETAILER_AUTO_IMPORT):
            return None
        operation_id = admit_operation(conn, kind="worker:retailer_import_queue")
        changed = conn.execute(text("""
            UPDATE retailer_import_queue
            SET status='processing', attempt_count=attempt_count+1,
                maintenance_operation_id=:operation_id,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND status='pending'
        """), {"id": row["id"], "operation_id": operation_id})
        if changed.rowcount != 1:
            raise RuntimeError("Winkelimportclaim is gelijktijdig gewijzigd")
        return {**dict(row), "operation_id": operation_id}


def _decode_claim(row: dict) -> RetailerReceiptEnvelope:
    # Decryption and canonical validation happen before any domain side effect.
    try:
        plaintext = _fernet().decrypt(row["payload_ciphertext"].encode("ascii"))
    except (InvalidToken, ValueError, TypeError) as exc:
        raise ValueError("decrypt_failed") from exc
    if hashlib.sha256(plaintext).hexdigest() != row["payload_sha256"]:
        raise ValueError("digest_mismatch")
    try:
        receipt = RetailerReceiptEnvelope.model_validate(json.loads(plaintext))
    except (ValueError, TypeError) as exc:
        raise ValueError("payload_invalid") from exc
    if (receipt.provider != row["provider"] or
            receipt.external_receipt_id != row["external_receipt_id"]):
        raise ValueError("identity_mismatch")
    return receipt


def _finish_review_without_side_effect(engine: Engine, row: dict, reason: str) -> None:
    """Only use for payload failures *before* calling canonical ingestion."""
    with engine.begin() as conn:
        changed = conn.execute(text("""
            UPDATE retailer_import_queue
            SET status='review_required', last_error_code=:reason,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND status='processing'
              AND maintenance_operation_id=:operation_id
        """), {"reason": reason, "id": row["id"], "operation_id": row["operation_id"]})
        if changed.rowcount != 1:
            raise RuntimeError("Winkelimportcontrole kon niet veilig worden opgeslagen")
        complete_operation(conn, operation_id=row["operation_id"])


def process_one_staged_receipt(engine: Engine, receipt_root: Path) -> bool:
    """Process exactly one durable claim; False means nothing is pending.

    Any failure after canonical ingestion begins remains `processing` with an
    unresolved operation. A crash at the final DB commit is handled the same
    way: an operator must prove the receipt side-effects before recovery.
    """
    if engine.dialect.name != "postgresql":
        return False
    with engine.connect() as conn:
        state = conn.execute(text("SELECT state FROM maintenance_control WHERE id=1")).scalar_one_or_none()
    if state not in {"normal", "announced"}:
        return False
    with engine.connect() as conn:
        if not is_platform_feature_enabled(conn, FEATURE_FLAG_RETAILER_AUTO_IMPORT):
            return False
    try:
        row = _claim_one(engine)
    except MaintenanceTransitionError:
        # Concurrent transition to draining wins over admission: expected pause.
        return False
    if row is None:
        return False
    token = _operation.set(row["operation_id"])
    try:
        try:
            envelope = _decode_claim(row)
        except ValueError as exc:
            # Exactly the four codes above; never use exception details as a
            # queue/log field, to avoid recording sensitive payload content.
            code = str(exc)
            if code not in {"decrypt_failed", "digest_mismatch", "payload_invalid", "identity_mismatch"}:
                raise
            _finish_review_without_side_effect(engine, row, code)
            return True

        result = import_retailer_receipt(
            engine, receipt_root,
            household_id=row["household_id"], envelope=envelope,
        )
        if not (result.get("raw_receipt_id") and
                (result.get("duplicate") in (True, False) or
                 result.get("refreshed_existing_receipt") is True)):
            raise RuntimeError("Onbekend resultaat na winkelimport")
        with engine.begin() as conn:
            changed = conn.execute(text("""
                UPDATE retailer_import_queue
                SET status='completed', raw_receipt_id=:receipt_id,
                    last_error_code=NULL, finished_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id AND status='processing'
                  AND maintenance_operation_id=:operation_id
            """), {
                "id": row["id"], "operation_id": row["operation_id"],
                "receipt_id": str(result["raw_receipt_id"]),
            })
            if changed.rowcount != 1:
                raise RuntimeError("Winkelimport kan niet ondubbelzinnig worden afgerond")
            complete_operation(conn, operation_id=row["operation_id"])
        return True
    finally:
        _operation.reset(token)


async def run_retailer_import_queue(engine: Engine, receipt_root: Path, stop: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=QUEUE_STARTUP_DELAY_SECONDS)
        return
    except asyncio.TimeoutError:
        pass
    while not stop.is_set():
        try:
            # One receipt per iteration. `to_thread` keeps blocking canonical
            # receipt ingestion off the event loop. Graceful shutdown awaits it.
            processed = await asyncio.to_thread(process_one_staged_receipt, engine, receipt_root)
        except Exception:
            # A persistent operation remains for domain reconciliation.
            # Never print receipt contents, IDs or crypto data in logs.
            LOGGER.warning("Retailer queue operation failed; maintenance review required")
            processed = False
        if processed:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=QUEUE_POLL_SECONDS)
        except asyncio.TimeoutError:
            pass


def register_retailer_import_queue(app, engine: Engine, receipt_root: Path) -> None:
    @app.on_event("startup")
    async def start_retailer_import_queue() -> None:
        stop = asyncio.Event()
        app.state.retailer_import_stop = stop
        app.state.retailer_import_task = asyncio.create_task(
            run_retailer_import_queue(engine, receipt_root, stop)
        )

    @app.on_event("shutdown")
    async def stop_retailer_import_queue() -> None:
        stop = getattr(app.state, "retailer_import_stop", None)
        task = getattr(app.state, "retailer_import_task", None)
        if stop is not None:
            stop.set()
        if task is not None:
            await task
