"""Atomic encrypted staging of retailer receipts already confirmed by a user.

This module intentionally does not start processing. A separate maintenance-
aware worker must exist and be verified before the staging API is exposed.
"""
from __future__ import annotations

import hashlib
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.integrations.retailer_receipts import RetailerReceiptEnvelope
from app.services.jumbo_receipt_validation import validate_jumbo_receipt_for_import
from app.services.retailer_account_secure_store import _fernet

MAX_STAGED_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_STAGED_JUMBO_BATCH = 10


def _checked_receipt(envelope: RetailerReceiptEnvelope) -> tuple[bytes, str]:
    if envelope.provider not in {"jumbo", "lidl"}:
        raise ValueError("Alleen bevestigde Jumbo- en Lidl-bonnen kunnen worden geparkeerd")
    if envelope.provider == "jumbo":
        validate_jumbo_receipt_for_import(envelope)
    source = envelope.stable_json_bytes()
    if len(source) > MAX_STAGED_RECEIPT_BYTES:
        raise ValueError("De winkelbon is te groot voor veilige opslag")
    return source, hashlib.sha256(source).hexdigest()


def stage_confirmed_receipts(
    engine: Engine, *, household_id: str,
    envelopes: list[RetailerReceiptEnvelope],
) -> list[dict[str, str]]:
    """All-or-none database staging. Never trust household identity in payload.

    A returned `queued` is **not** proof of successful Kassa ingestion.
    Repeated receipt+content returns the existing queue identity.
    """
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Duurzame winkelimport vereist PostgreSQL")
    if not household_id or not envelopes or len(envelopes) > MAX_STAGED_JUMBO_BATCH:
        raise ValueError("Ongeldige of te grote bevestigde bonnenbatch")
    checked = [_checked_receipt(envelope) for envelope in envelopes]
    identities = [(envelope.provider, envelope.external_receipt_id) for envelope in envelopes]
    if len(set(identities)) != len(identities):
        raise ValueError("Dubbel bonnummer in bevestigde winkelbatch")
    providers = {receipt.provider for receipt in envelopes}
    if len(providers) != 1 or ("lidl" in providers and len(envelopes) != 1):
        raise ValueError("Lidl-bonnen afzonderlijk aanleveren; Jumbo-batch maximaal tien")
    # Encrypt before entering the transaction. The same stable digest is used
    # only for an idempotency comparison and never exposes receipt plaintext.
    encrypted = [_fernet().encrypt(body).decode("ascii") for body, _ in checked]

    results = []
    with engine.begin() as conn:
        for envelope, (_, digest), ciphertext in zip(envelopes, checked, encrypted):
            queue_id = str(uuid4())
            row = conn.execute(text("""
                INSERT INTO retailer_import_queue
                  (id, household_id, provider, external_receipt_id,
                   payload_sha256, payload_ciphertext)
                VALUES (:id, :household_id, :provider, :external_receipt_id,
                        :payload_sha256, :payload_ciphertext)
                ON CONFLICT (household_id,provider,external_receipt_id,payload_sha256)
                  DO NOTHING
                RETURNING id,status
            """), {
                "id": queue_id,
                "household_id": household_id,
                "provider": envelope.provider,
                "external_receipt_id": envelope.external_receipt_id,
                "payload_sha256": digest,
                "payload_ciphertext": ciphertext,
            }).mappings().first()
            if row is None:
                row = conn.execute(text("""
                    SELECT id,status FROM retailer_import_queue
                    WHERE household_id=:household_id AND provider=:provider
                      AND external_receipt_id=:external_receipt_id
                      AND payload_sha256=:payload_sha256
                """), {
                    "household_id": household_id,
                    "provider": envelope.provider,
                    "external_receipt_id": envelope.external_receipt_id,
                    "payload_sha256": digest,
                }).mappings().one()
            results.append({"queue_id": str(row["id"]), "status": str(row["status"])})
    return results
