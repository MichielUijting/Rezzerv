"""Lidl Plus digital receipt account synchronization service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from app.integrations.retailer_accounts import LidlReceiptClient, build_lidl_login_attempt
from app.services.retailer_account_runtime_store import (
    delete_lidl_auth_attempt,
    delete_lidl_session,
    get_lidl_auth_attempt,
    get_lidl_session,
    lidl_session_status,
    set_lidl_auth_attempt,
    set_lidl_session,
)
from app.services.retailer_receipt_import_service import import_retailer_receipt


def start_lidl_account_connection(*, household_id: str) -> dict[str, Any]:
    attempt = build_lidl_login_attempt(country="NL", language="nl")
    set_lidl_auth_attempt(household_id, attempt)
    return {
        **lidl_session_status(household_id),
        "login_url": attempt.login_url,
        "redirect_uri": "com.lidlplus.app://callback",
    }


def connect_lidl_account(
    *,
    household_id: str,
    callback_url: str,
    client: LidlReceiptClient | None = None,
) -> dict[str, Any]:
    attempt = get_lidl_auth_attempt(household_id)
    if attempt is None:
        raise ValueError("Start eerst een nieuwe Lidl-login vanuit Inhuis")
    owns_client = client is None
    active_client = client or LidlReceiptClient(country="NL", language="nl")
    try:
        session = active_client.exchange_code(callback_url, attempt)
        set_lidl_session(household_id, session)
        delete_lidl_auth_attempt(household_id)
        return lidl_session_status(household_id)
    finally:
        if owns_client:
            active_client.close()


def disconnect_lidl_account(*, household_id: str) -> dict[str, Any]:
    delete_lidl_auth_attempt(household_id)
    delete_lidl_session(household_id)
    return lidl_session_status(household_id)


def sync_lidl_receipts(
    engine: Engine,
    receipt_storage_root: Path,
    *,
    household_id: str,
    limit: int = 20,
    client: LidlReceiptClient | None = None,
) -> dict[str, Any]:
    session = get_lidl_session(household_id)
    if session is None:
        raise ValueError("Lidl Plus-account is niet gekoppeld")

    owns_client = client is None
    active_client = client or LidlReceiptClient(country=session.country, language=session.language)
    try:
        session, summaries = active_client.list_receipts(session, limit=limit)
        set_lidl_session(household_id, session)

        imported: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for summary in summaries:
            try:
                session, envelope = active_client.get_receipt_envelope(session, summary)
                set_lidl_session(household_id, session)
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
                errors.append(
                    {
                        "external_receipt_id": summary.receipt_id,
                        "error": str(exc),
                    }
                )

        return {
            "provider": "lidl",
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
