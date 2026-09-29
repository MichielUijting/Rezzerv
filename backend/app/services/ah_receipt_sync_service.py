"""
Albert Heijn digital receipt account synchronization service.

Account credentials remain runtime-only. Receipt observations are handed to the
existing retailer receipt ingestion service so Kassa/Uitpakken/Voorraad keep
their existing authority and behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from app.integrations.retailer_accounts import AHReceiptClient
from app.services.retailer_account_runtime_store import (
    ah_session_status,
    delete_ah_session,
    get_ah_session,
    set_ah_session,
)
from app.services.retailer_receipt_import_service import import_retailer_receipt


def connect_ah_account(
    *,
    household_id: str,
    code_or_redirect: str,
    client: AHReceiptClient | None = None,
) -> dict[str, Any]:
    owns_client = client is None
    active_client = client or AHReceiptClient()
    try:
        session = active_client.exchange_code(code_or_redirect)
        set_ah_session(household_id, session)
        return ah_session_status(household_id)
    finally:
        if owns_client:
            active_client.close()


def disconnect_ah_account(*, household_id: str) -> dict[str, Any]:
    delete_ah_session(household_id)
    return ah_session_status(household_id)


def sync_ah_receipts(
    engine: Engine,
    receipt_storage_root: Path,
    *,
    household_id: str,
    limit: int = 20,
    client: AHReceiptClient | None = None,
) -> dict[str, Any]:
    session = get_ah_session(household_id)
    if session is None:
        raise ValueError("Albert Heijn-account is niet gekoppeld")

    owns_client = client is None
    active_client = client or AHReceiptClient()
    try:
        session, summaries = active_client.list_receipts(session, limit=limit)
        set_ah_session(household_id, session)

        imported: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for summary in summaries:
            try:
                session, envelope = active_client.get_receipt_envelope(session, summary)
                set_ah_session(household_id, session)
                result = import_retailer_receipt(
                    engine,
                    receipt_storage_root,
                    household_id=household_id,
                    envelope=envelope,
                )
                imported.append(
                    {
                        "external_receipt_id": envelope.external_receipt_id,
                        "date_time": summary.date_time,
                        "total_amount": summary.total_amount,
                        "ingest": result,
                    }
                )
            except Exception as exc:
                # Never expose token material. Receipt IDs are provider object IDs
                # and are sufficient to identify the failed receipt.
                errors.append(
                    {
                        "external_receipt_id": summary.receipt_id,
                        "error": str(exc),
                    }
                )

        return {
            "provider": "ah",
            "receipts_found": len(summaries),
            "receipts_processed": len(imported),
            "receipts_failed": len(errors),
            "receipts": imported,
            "errors": errors,
            "persistence": "runtime_only",
        }
    finally:
        if owns_client:
            active_client.close()
