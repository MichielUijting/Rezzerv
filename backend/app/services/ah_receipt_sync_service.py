"""Albert Heijn digital receipt account synchronization service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from app.integrations.retailer_accounts import AHReceiptClient
from app.services.retailer_account_secure_store import (
    ah_session_status,
    delete_ah_session,
    get_ah_session,
    get_known_ah_receipt_ids,
    mark_ah_receipts_synced,
    save_ah_session,
    touch_ah_sync,
)
from app.services.retailer_receipt_import_service import import_retailer_receipt


def connect_ah_account(
    engine: Engine,
    *,
    household_id: str,
    code_or_redirect: str,
    client: AHReceiptClient | None = None,
) -> dict[str, Any]:
    owns_client = client is None
    active_client = client or AHReceiptClient()
    try:
        session = active_client.exchange_code(code_or_redirect)
        save_ah_session(engine, household_id, session)
        return ah_session_status(engine, household_id)
    finally:
        if owns_client:
            active_client.close()


def disconnect_ah_account(engine: Engine, *, household_id: str) -> dict[str, Any]:
    delete_ah_session(engine, household_id)
    return ah_session_status(engine, household_id)



def count_pending_ah_receipts(
    engine: Engine,
    *,
    household_id: str,
    limit: int = 100,
    client: AHReceiptClient | None = None,
) -> dict[str, Any]:
    """Count AH receipts that can still be imported without importing them."""
    session = get_ah_session(engine, household_id)
    if session is None:
        return {
            "provider": "ah",
            "connected": False,
            "count_available": True,
            "pending_downloads": 0,
            "receipts_found": 0,
        }

    owns_client = client is None
    active_client = client or AHReceiptClient()
    try:
        session, summaries = active_client.list_receipts(session, limit=limit)
        save_ah_session(engine, household_id, session)
        known_ids = get_known_ah_receipt_ids(engine, household_id)
        pending = [summary for summary in summaries if summary.receipt_id not in known_ids]
        return {
            "provider": "ah",
            "connected": True,
            "count_available": True,
            "pending_downloads": len(pending),
            "receipts_found": len(summaries),
        }
    finally:
        if owns_client:
            active_client.close()

def _safe_ah_import_failure_reason(exc: Exception, stage: str) -> str:
    """Public diagnostic category; never return raw provider/receipt error messages."""
    if stage != "import":
        return "detail_request_failed"
    if not isinstance(exc, ValueError):
        return "other_import_failure"
    message = str(exc).lower()
    if "geen artikelregels" in message:
        return "missing_article_lines"
    if "geen bruikbaar totaalbedrag" in message:
        return "missing_total_amount"
    if "niet als bruikbare kassabon herkend" in message:
        return "receipt_not_recognized"
    if "bron is niet actief" in message:
        return "inactive_source"
    return "other_validation_failure"


def sync_ah_receipts(
    engine: Engine,
    receipt_storage_root: Path,
    *,
    household_id: str,
    limit: int = 100,
    client: AHReceiptClient | None = None,
) -> dict[str, Any]:
    session = get_ah_session(engine, household_id)
    if session is None:
        raise ValueError("Albert Heijn-account is niet gekoppeld")

    owns_client = client is None
    active_client = client or AHReceiptClient()
    try:
        session, summaries = active_client.list_receipts(session, limit=limit)
        save_ah_session(engine, household_id, session)

        known_ids = get_known_ah_receipt_ids(engine, household_id)
        pending = [summary for summary in summaries if summary.receipt_id not in known_ids]

        imported: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        completed_ids: set[str] = set()

        for summary in pending:
            stage = "details"
            envelope = None
            try:
                session, envelope = active_client.get_receipt_envelope(session, summary)
                save_ah_session(engine, household_id, session)
                stage = "import"
                result = import_retailer_receipt(
                    engine,
                    receipt_storage_root,
                    household_id=household_id,
                    envelope=envelope,
                )
                completed_ids.add(envelope.external_receipt_id)
                imported.append(
                    {
                        "external_receipt_id": envelope.external_receipt_id,
                        "date_time": summary.date_time,
                        "total_amount": summary.total_amount,
                        "ingest": result,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "external_receipt_id": summary.receipt_id,
                        "date_time": summary.date_time,
                        "transaction_type": None,  # AH does not supply a verified type in the current contract.
                        "error": str(exc),
                        "stage": stage,
                        "error_type": type(exc).__name__,
                        "reason_code": _safe_ah_import_failure_reason(exc, stage),
                        "structure_diagnostic": (
                            envelope.receipt.get("_ah_structure_diagnostic")
                            if stage == "import"
                            and envelope is not None
                            and _safe_ah_import_failure_reason(exc, stage) == "missing_article_lines"
                            else None
                        ),
                    }
                )

        if completed_ids:
            mark_ah_receipts_synced(engine, household_id, completed_ids)
        else:
            touch_ah_sync(engine, household_id)

        return {
            "provider": "ah",
            "receipts_found": len(summaries),
            "receipts_new": len(pending),
            "receipts_skipped_known": len(summaries) - len(pending),
            "receipts_processed": len(imported),
            "receipts_failed": len(errors),
            "receipts": imported,
            "errors": errors,
            "persistence": "encrypted_database",
            "last_sync_at": ah_session_status(engine, household_id).get("last_sync_at"),
        }
    finally:
        if owns_client:
            active_client.close()
