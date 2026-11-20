"""Isolated DML-only PostgreSQL proof for historical receipt inventory boundaries.

Uses the already-migrated ephemeral PostgreSQL CI database, performs all seed
operations in one transaction, and deliberately ALWAYS rolls that transaction
back. No schema changes or deletes of previously existing data are possible.
"""
from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.receipt_historical_import_policy import (
    activate_cutover_for_new_onboarding,
    classify_receipt_for_household,
    read_household_cutover,
    require_batch_inventory_allowed,
)


def _id() -> str:
    return str(uuid4())


def _seed_household(conn) -> str:
    household_id = _id()
    conn.execute(text("""
        INSERT INTO household_registry (id, naam)
        VALUES (:id, 'Historische bonnen CI')
    """), {"id": household_id})
    return household_id


def _seed_provider_and_connection(conn, household_id: str) -> tuple[str, str]:
    provider_id = conn.execute(text(
        "SELECT id FROM store_providers WHERE code = 'receipt' LIMIT 1"
    )).scalar_one_or_none()
    if not provider_id:
        provider_id = _id()
        conn.execute(text("""
            INSERT INTO store_providers (
                id, code, name, status, import_mode
            ) VALUES (:id, 'receipt', 'Bonimport CI', 'active', 'mock')
        """), {"id": provider_id})
    connection_id = _id()
    conn.execute(text("""
        INSERT INTO household_store_connections (
            id, household_id, store_provider_id, connection_status
        ) VALUES (:id, :household_id, :provider_id, 'active')
    """), {
        "id": connection_id,
        "household_id": household_id,
        "provider_id": str(provider_id),
    })
    return str(provider_id), connection_id


def _seed_receipt(
    conn, *, household_id: str, provider_id: str,
    connection_id: str, store: str, purchase_date: date | None,
    purchase_at_source: str = "retailer",
) -> tuple[str, str]:
    source_id, raw_id, receipt_id, batch_id = (_id() for _ in range(4))
    conn.execute(text("""
        INSERT INTO receipt_sources (id, household_id, type, label)
        VALUES (:id, :household_id, 'retailer_api', :label)
    """), {"id": source_id, "household_id": household_id, "label": store})
    conn.execute(text("""
        INSERT INTO raw_receipts (
            id, household_id, source_id, original_filename, mime_type,
            storage_path, sha256_hash
        ) VALUES (
            :id, :household_id, :source_id, :filename, 'application/json',
            :storage_path, :sha256_hash
        )
    """), {
        "id": raw_id,
        "household_id": household_id,
        "source_id": source_id,
        "filename": receipt_id + ".json",
        "storage_path": "ci-only://" + receipt_id,
        "sha256_hash": hashlib.sha256(receipt_id.encode()).hexdigest(),
    })
    conn.execute(text("""
        INSERT INTO receipt_tables (
            id, raw_receipt_id, household_id, store_name,
            purchase_at, purchase_at_source,
            parse_status, approved_at, line_count
        ) VALUES (
            :id, :raw_id, :household_id, :store,
            :purchase_at, :purchase_at_source,
            'approved', CURRENT_TIMESTAMP, 1
        )
    """), {
        "id": receipt_id,
        "raw_id": raw_id,
        "household_id": household_id,
        "store": store,
        "purchase_at": (
            datetime.combine(purchase_date, datetime.min.time())
            if purchase_date else None
        ),
        "purchase_at_source": purchase_at_source,
    })
    conn.execute(text("""
        INSERT INTO purchase_import_batches (
            id, household_id, store_provider_id, connection_id,
            source_type, source_reference, import_status, raw_payload
        ) VALUES (
            :id, :household_id, :provider_id, :connection_id,
            'receipt', :reference, 'new', '{}'
        )
    """), {
        "id": batch_id,
        "household_id": household_id,
        "provider_id": provider_id,
        "connection_id": connection_id,
        "reference": "receipt:" + receipt_id,
    })
    return receipt_id, batch_id


def main() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Deze DML-test mag uitsluitend in de geïsoleerde GitHub CI draaien")
    if os.environ.get("MIGRATION_DATABASE_URL"):
        raise RuntimeError("DML-only toets mag geen migratiecredentials ontvangen")
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url or make_url(raw_url).get_backend_name() != "postgresql":
        raise RuntimeError("Geïsoleerde PostgreSQL-runtime is verplicht")

    engine = create_engine(raw_url, future=True)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                new_household = _seed_household(conn)
                other_household = _seed_household(conn)
                assert activate_cutover_for_new_onboarding(
                    conn, household_id=new_household
                )
                assert read_household_cutover(conn, new_household)
                assert read_household_cutover(conn, other_household) is None
                assert not activate_cutover_for_new_onboarding(
                    conn, household_id=new_household
                )
                first_current = read_household_cutover(conn, new_household)
                assert isinstance(first_current, date)

                provider, connection = _seed_provider_and_connection(
                    conn, new_household,
                )
                old_count = 0
                for i in range(100):
                    store = ("Albert Heijn", "Lidl", "Jumbo")[i % 3]
                    receipt_id, batch_id = _seed_receipt(
                        conn, household_id=new_household,
                        provider_id=provider, connection_id=connection,
                        store=store,
                        purchase_date=first_current - timedelta(days=1 + i % 30),
                    )
                    assert classify_receipt_for_household(
                        conn, household_id=new_household,
                        receipt_table_id=receipt_id,
                    ) == "historical"
                    try:
                        require_batch_inventory_allowed(
                            conn, household_id=new_household, batch_id=batch_id,
                        )
                    except HTTPException as exc:
                        assert exc.status_code == 409
                    else:
                        raise AssertionError("Historische bon kan voorraad bijschrijven")
                    old_count += 1
                assert old_count == 100
                # These receipts are preserved but must not be presented as
                # pending Kassa or Uitpakken work. Read-only SQL contract.
                for operation in ("AND rt.approved_at IS NULL", "AND rt.approved_at IS NOT NULL"):
                    current_visible = conn.execute(text("""
                        SELECT COUNT(*) FROM receipt_tables rt
                        LEFT JOIN household_receipt_history_cutovers hrc
                          ON hrc.household_id = rt.household_id
                        WHERE rt.household_id=:household_id
                          """ + operation + """
                          AND (
                            hrc.household_id IS NULL OR rt.purchase_at IS NULL
                            OR lower(trim(COALESCE(rt.purchase_at_source,''))) = 'import_default'
                            OR CAST(rt.purchase_at AS DATE) >= hrc.first_current_purchase_date
                          )
                    """), {"household_id": new_household}).scalar_one()
                    assert current_visible == 0, operation
                historical_count = conn.execute(text("""
                    SELECT COUNT(*) FROM receipt_tables rt
                    JOIN household_receipt_history_cutovers hrc
                      ON hrc.household_id=rt.household_id
                    WHERE rt.household_id=:household_id
                      AND rt.purchase_at IS NOT NULL
                      AND CAST(rt.purchase_at AS DATE) < hrc.first_current_purchase_date
                """), {"household_id": new_household}).scalar_one()
                assert historical_count == 100
                print("RECEIPT_HISTORY_POSTGRESQL_100_HISTORICAL_BLOCKED_GREEN")

                recent_id, recent_batch = _seed_receipt(
                    conn, household_id=new_household,
                    provider_id=provider, connection_id=connection,
                    store="Albert Heijn", purchase_date=first_current,
                )
                assert classify_receipt_for_household(
                    conn, household_id=new_household,
                    receipt_table_id=recent_id,
                ) == "current"
                require_batch_inventory_allowed(
                    conn, household_id=new_household, batch_id=recent_batch,
                )

                missing_id, missing_batch = _seed_receipt(
                    conn, household_id=new_household,
                    provider_id=provider, connection_id=connection,
                    store="Jumbo", purchase_date=None,
                    purchase_at_source="import_default",
                )
                assert classify_receipt_for_household(
                    conn, household_id=new_household,
                    receipt_table_id=missing_id,
                ) == "review_required"
                try:
                    require_batch_inventory_allowed(
                        conn, household_id=new_household, batch_id=missing_batch,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 409
                else:
                    raise AssertionError("Onzekere datum mag niet naar voorraad")
                print("RECEIPT_HISTORY_POSTGRESQL_CUTOFF_AND_MISSING_DATE_GREEN")

                other_provider, other_connection = _seed_provider_and_connection(
                    conn, other_household,
                )
                other_receipt, other_batch = _seed_receipt(
                    conn, household_id=other_household,
                    provider_id=other_provider, connection_id=other_connection,
                    store="Lidl",
                    purchase_date=first_current - timedelta(days=30),
                )
                assert classify_receipt_for_household(
                    conn, household_id=other_household,
                    receipt_table_id=other_receipt,
                ) == "legacy"
                require_batch_inventory_allowed(
                    conn, household_id=other_household, batch_id=other_batch,
                )
                # A forged receipt reference from the other household must not
                # be usable to authorize this household's stock processing.
                conn.execute(text("""
                    UPDATE purchase_import_batches
                    SET source_reference = :reference
                    WHERE id = :batch_id AND household_id = :household_id
                """), {
                    "reference": "receipt:" + other_receipt,
                    "batch_id": missing_batch,
                    "household_id": new_household,
                })
                try:
                    require_batch_inventory_allowed(
                        conn, household_id=new_household, batch_id=missing_batch,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 409
                else:
                    raise AssertionError("Cross-household receipt boundary bypass")
                print("RECEIPT_HISTORY_POSTGRESQL_HOUSEHOLD_ISOLATION_GREEN")

                # This proof uses real, canonical storage but does not invoke
                # the stock API: it establishes that no stock is synthesized
                # by history activation, retention or validation alone.
                for table in ("inventory", "inventory_events"):
                    count = conn.execute(text(
                        f"SELECT COUNT(*) FROM {table} WHERE household_id=:household_id"
                    ), {"household_id": new_household}).scalar_one()
                    assert count == 0, f"Historical receipts mutated {table}"
                print("RECEIPT_HISTORY_POSTGRESQL_ZERO_STOCK_MUTATION_GREEN")
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    print("RECEIPT_HISTORY_POSTGRESQL_TRANSACTION_ROLLBACK_GREEN")


if __name__ == "__main__":
    main()
