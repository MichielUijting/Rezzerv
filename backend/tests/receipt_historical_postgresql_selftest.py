"""Isolated DML-only PostgreSQL proof for historical receipt inventory boundaries.

Uses the already-migrated ephemeral PostgreSQL CI database, performs all seed
operations in one transaction, and deliberately ALWAYS rolls that transaction
back. No schema changes or deletes of previously existing data are possible.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import time
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from unittest.mock import patch
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
    purchase_at_source: str = "detected",
    approved: bool = True,
    with_line: bool = False,
) -> tuple[str, str]:
    source_id, raw_id, receipt_id, batch_id = (_id() for _ in range(4))
    conn.execute(text("""
        INSERT INTO receipt_sources (id, household_id, type, label, is_active)
        VALUES (:id, :household_id, 'retailer_api', :label, TRUE)
    """), {"id": source_id, "household_id": household_id, "label": store})
    conn.execute(text("""
        INSERT INTO raw_receipts (
            id, household_id, source_id, original_filename, mime_type,
            storage_path, sha256_hash, raw_status
        ) VALUES (
            :id, :household_id, :source_id, :filename, 'application/json',
            :storage_path, :sha256_hash, 'imported'
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
            purchase_at, purchase_at_source, logical_receipt_key,
            workflow_state, currency, parse_status, approved_at, line_count
        ) VALUES (
            :id, :raw_id, :household_id, :store,
            :purchase_at, :purchase_at_source, :logical_key,
            'active', 'EUR',
            CASE WHEN :approved THEN 'approved' ELSE 'parsed' END,
            CASE WHEN :approved THEN CURRENT_TIMESTAMP ELSE NULL END, 1
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
        "logical_key": _id(),
        "approved": approved,
    })
    if with_line:
        conn.execute(text("""
            INSERT INTO receipt_table_lines (
                id, receipt_table_id, line_index, raw_label, normalized_label,
                quantity, unit, line_total, article_match_status, logical_line_key
            ) VALUES (
                :id, :receipt_id, 0, 'CI volkorenrijst', 'ci volkorenrijst',
                1, 'stuk', 2.00, 'unmatched', :line_key
            )
        """), {"id": _id(), "receipt_id": receipt_id, "line_key": _id()})
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



def _prove_historical_workflows(
    conn, *, main, household_id: str, provider_id: str,
    connection_id: str, cutover: date,
) -> None:
    """Exercise actual Kassa/Uitpakken projections, approval and date routes.

    Only authorization/connection ownership and response serialization are
    mocked: all receipt classification, SQL mutations and route filtering run
    on canonical ephemeral PostgreSQL tables within the outer rollback.
    """
    from app.api import kassa_pagination_routes as kassa

    historic_id, historic_batch = _seed_receipt(
        conn, household_id=household_id, provider_id=provider_id,
        connection_id=connection_id, store="Lidl",
        purchase_date=cutover - timedelta(days=8),
        approved=False, with_line=True,
    )
    fresh_id, fresh_batch = _seed_receipt(
        conn, household_id=household_id, provider_id=provider_id,
        connection_id=connection_id, store="Jumbo",
        purchase_date=cutover, approved=False, with_line=True,
    )
    undated_id, _ = _seed_receipt(
        conn, household_id=household_id, provider_id=provider_id,
        connection_id=connection_id, store="Albert Heijn",
        purchase_date=None, purchase_at_source="import_default", approved=False,
        with_line=True,
    )

    class _TransactionEngine:
        def begin(self):
            return nullcontext(conn)

        def connect(self):
            return nullcontext(conn)

    def _authorized_receipt(_conn, receipt_table_id, _authorization):
        owner = _conn.execute(text("""
            SELECT household_id FROM receipt_tables
            WHERE id = :id
        """), {"id": receipt_table_id}).scalar_one()
        assert str(owner) == household_id
        return {"active_household_id": household_id, "email": "ci@invalid.example"}

    def _noop_detail(receipt_table_id, _authorization):
        return {"receipt_table_id": receipt_table_id}

    # The actual production endpoints are registered by the canonical startup.
    approval_routes = [
        r for r in main.app.routes
        if getattr(r, "path", "") == "/api/receipts/{receipt_table_id}/approve"
        and "POST" in (getattr(r, "methods", set()) or set())
    ]
    assert len(approval_routes) == 1
    with (
        patch.object(main, "engine", _TransactionEngine()),
        patch.object(kassa, "engine", _TransactionEngine()),
        patch.object(main, "require_receipt_write_context", side_effect=_authorized_receipt),
        patch.object(main, "get_receipt_detail", side_effect=_noop_detail),
        patch.object(main, "resolve_authorized_household_id", return_value=household_id),
        patch.object(main, "ensure_default_receipt_sources"),
        patch.object(main, "_auto_approve_pending_receipts_for_household"),
    ):
        original_data_count = conn.execute(text("""
            SELECT COUNT(*) FROM receipt_tables
            WHERE household_id=:home AND deleted_at IS NULL
        """), {"home": household_id}).scalar_one()

        kassa_before = kassa.list_kassa_receipts_page(
            householdId=household_id, page=1, page_size=10,
            focus_receipt_id="", winkel="", datum="", totaal="",
            artikelen="", status="", zoek="", time_zone="UTC",
            sort_key="date", sort_direction="desc", initialize=False,
            authorization="ci-token",
        )
        active_ids = {str(x.get("receipt_table_id") or x.get("id"))
                      for x in kassa_before["items"]}
        assert historic_id not in active_ids
        assert fresh_id in active_ids
        assert undated_id in active_ids
        print("RECEIPT_HISTORY_POSTGRESQL_KASSA_PROJECTION_GREEN")

        history = kassa.list_historical_kassa_receipts(
            householdId=household_id, page=1, page_size=100,
            authorization="ci-token",
        )
        assert history["total"] >= 101
        assert any(x["receipt_table_id"] == historic_id for x in history["items"]) or history["total"] > 100
        assert all(x["receipt_table_id"] != fresh_id for x in history["items"])
        assert conn.execute(text("""
            SELECT COUNT(*) FROM receipt_tables
            WHERE household_id=:home AND deleted_at IS NULL
        """), {"home": household_id}).scalar_one() == original_data_count
        print("RECEIPT_HISTORY_POSTGRESQL_HISTORICAL_READONLY_GREEN")

        # Approval uses the registered production wrapper, including the real
        # canonical approval SQL and batch synchronization. No stock mutation.
        result = approval_routes[0].endpoint(historic_id, "ci-token")
        assert result["approval_destination"] == "history"
        approved_at = conn.execute(text(
            "SELECT approved_at FROM receipt_tables WHERE id=:id"
        ), {"id": historic_id}).scalar_one()
        assert approved_at is not None
        count_before = conn.execute(text("""
            SELECT COUNT(*) FROM purchase_import_batches
            WHERE household_id=:home AND source_reference=:ref
        """), {"home": household_id, "ref": "receipt:" + historic_id}).scalar_one()
        repeated = approval_routes[0].endpoint(historic_id, "ci-token")
        assert repeated["approval_destination"] == "history"
        count_after = conn.execute(text("""
            SELECT COUNT(*) FROM purchase_import_batches
            WHERE household_id=:home AND source_reference=:ref
        """), {"home": household_id, "ref": "receipt:" + historic_id}).scalar_one()
        assert count_before == count_after == 1
        print("RECEIPT_HISTORY_POSTGRESQL_MANUAL_APPROVAL_IDEMPOTENT_GREEN")

        unpacked = main.list_unpack_start_batches(
            householdId=household_id, page=1, page_size=100,
            winkel="", datum="", regels="", status="",
            sort_key="datum", sort_direction="desc", authorization="ci-token",
        )
        assert all(x.get("receipt_table_id") != historic_id
                   for x in unpacked["items"])
        print("RECEIPT_HISTORY_POSTGRESQL_UNPACK_PROJECTION_GREEN")

        # Re-importing the same physical purchase is still classified by its
        # original purchase date. No hidden 'today' stock write is allowed.
        duplicate_id, duplicate_batch = _seed_receipt(
            conn, household_id=household_id, provider_id=provider_id,
            connection_id=connection_id, store="Lidl",
            purchase_date=cutover - timedelta(days=8), approved=False, with_line=True,
        )
        assert classify_receipt_for_household(
            conn, household_id=household_id, receipt_table_id=duplicate_id,
        ) == "historical"
        try:
            require_batch_inventory_allowed(
                conn, household_id=household_id, batch_id=duplicate_batch,
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Re-ingested historic purchase was accepted")
        print("RECEIPT_HISTORY_POSTGRESQL_REIMPORT_BOUNDARY_GREEN")

        # When a current bon has already been recorded as processed, an
        # ordinary date edit must not silently reclassify its inventory.
        conn.execute(text("""
            INSERT INTO purchase_import_lines (
                id, batch_id, external_line_ref, article_name_raw, quantity_raw,
                match_status, review_decision, processing_status
            ) VALUES (
                :id, :batch_id, :ref, 'CI rijst', 1,
                'unmatched', 'selected', 'processed'
            )
        """), {"id": _id(), "batch_id": fresh_batch, "ref": _id()})
        try:
            main.update_receipt_header(
                fresh_id, main.ReceiptHeaderUpdateRequest(
                    purchase_at=(cutover - timedelta(days=8)).isoformat(),
                ), "ci-token",
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Already processed purchase backdated silently")
        actual = conn.execute(text(
            "SELECT CAST(purchase_at AS DATE) FROM receipt_tables WHERE id=:id"
        ), {"id": fresh_id}).scalar_one()
        assert actual == cutover
        print("RECEIPT_HISTORY_POSTGRESQL_BACKDATE_GUARD_GREEN")

        # The retained historical receipt and all its lines remain available,
        # while neither first approval nor replay creates stock.
        for name in ("inventory", "inventory_events"):
            assert conn.execute(text(
                f"SELECT COUNT(*) FROM {name} WHERE household_id=:home"
            ), {"home": household_id}).scalar_one() == 0



def _prove_pr732_historical_identity_recovery(
    conn, *, household_id, other_household, provider_id, connection_id, cutover,
):
    """Current PostgreSQL uniquely prevents two active catalog-linked owners."""
    from sqlalchemy.exc import IntegrityError
    from app.services.global_product_service import get_or_create_global_product

    product = get_or_create_global_product(
        conn, gtin=None, name="PR732 catalog uniqueness " + _id(), source="ci",
    )
    first, duplicate = _id(), _id()
    conn.execute(text("""
        INSERT INTO household_articles (
            id, household_id, naam, consumable, global_product_id, status
        ) VALUES (:id,:home,'PR732 catalog unique',1,:product,'active')
    """), {"id": first, "home": household_id, "product": product})
    try:
        with conn.begin_nested():
            conn.execute(text("""
                INSERT INTO household_articles (
                    id, household_id, naam, consumable, global_product_id, status
                ) VALUES (:id,:home,'PR732 catalog duplicate',1,:product,'active')
            """), {"id": duplicate, "home": household_id, "product": product})
    except IntegrityError:
        pass
    else:
        raise AssertionError(
            "The current PostgreSQL schema must prevent a duplicate active catalog match"
        )
    assert conn.execute(text("""
        SELECT COUNT(*) FROM household_articles
        WHERE household_id=:home AND global_product_id=:product
          AND COALESCE(status,'active')='active'
    """), {"home": household_id, "product": product}).scalar_one() == 1
    print("PR732_POSTGRESQL_CATALOG_UNIQUE_GUARD_GREEN")


def _prove_pr732_verified_gtin_recovery(conn, *, cutoff):
    """Real DML-only PostgreSQL: AH/Jumbo GTIN proof, manual guard, idempotence."""
    from app.services.historical_household_stock_writer import refresh_automatic_historical_stock
    from app.services.historical_household_purchase_cadence import (
        read_historical_household_purchase_cadence,
    )

    home, other_home = _seed_household(conn), _seed_household(conn)
    assert activate_cutover_for_new_onboarding(conn, household_id=home)
    provider, connection = _seed_provider_and_connection(conn, home)
    conn.execute(text("""
        INSERT INTO household_settings (id,household_id,setting_key,setting_value)
        VALUES (:id,:home,'consumable_auto_deduction_mode','consume_all_existing_before_purchase')
    """), {"id": _id(), "home": home})
    conn.execute(text("""
        INSERT INTO household_settings (id,household_id,setting_key,setting_value)
        VALUES (:id,:home,'almost_out_prediction_days','100')
    """), {"id": _id(), "home": home})
    conn.execute(text("""
        INSERT INTO household_settings (id,household_id,setting_key,setting_value)
        VALUES (:id,:home,'almost_out_prediction_enabled','true')
    """), {"id": _id(), "home": home})

    winner, duplicate = sorted((_id(), _id()))
    protected, manual = sorted((_id(), _id()))
    for article_id, name in (
        (winner, "PR732 EAN without catalog"),
        (duplicate, "PR732 EAN without catalog"),
        (protected, "PR732 different manual item"),
        (manual, "PR732 different manual item"),
    ):
        conn.execute(text("""
            INSERT INTO household_articles (
                id, household_id, naam, consumable, status
            ) VALUES (:id,:home,:name,1,'active')
        """), {"id": article_id, "home": home, "name": name})
    foreign_id = _id()
    conn.execute(text("""
        INSERT INTO household_articles (id,household_id,naam,consumable,status)
        VALUES (:id,:home,'PR732 other EAN household',1,'active')
    """), {"id": foreign_id, "home": other_home})

    # The classification review is a production PostgreSQL SELECT over an
    # INTEGER 0/1/NULL column. Review must never mutate the article itself.
    review_id = _id()
    conn.execute(text("""
        INSERT INTO household_articles (id,household_id,naam,consumable,status)
        VALUES (:id,:home,'Verse halfvolle melk',0,'active')
    """), {"id": review_id, "home": home})
    from app.services.household_consumable_review import list_consumable_review_candidates
    review = list_consumable_review_candidates(
        conn, household_id=home, limit=10, offset=0,
    )
    assert review["total"] == 1 and review["items"][0]["id"] == review_id, review
    assert review["items"][0]["consumable"] is False, review
    assert conn.execute(text("""
        SELECT consumable FROM household_articles
        WHERE household_id=:home AND id=:id
    """), {"home": home, "id": review_id}).scalar_one() == 0
    print("PR732_POSTGRESQL_CONSUMABLE_REVIEW_GREEN")

    receipt_ids = []
    for days_ago, store, store_code, article_id, barcode in (
        (35, "Albert Heijn", "ah", winner, "4006381333931"),
        (20, "Jumbo", "jumbo", duplicate, "4006381333931"),
        (36, "Albert Heijn", "ah", protected, "5901234123457"),
        (21, "Jumbo", "jumbo", manual, "5901234123457"),
    ):
        receipt_id, _ = _seed_receipt(
            conn, household_id=home, provider_id=provider,
            connection_id=connection, store=store,
            purchase_date=cutoff - timedelta(days=days_ago), with_line=True,
        )
        receipt_ids.append(receipt_id)
        conn.execute(text("""
            UPDATE receipt_sources rs
            SET source_path=:store_code
            FROM raw_receipts rr
            JOIN receipt_tables rt ON rt.raw_receipt_id=rr.id
            WHERE rt.id=:receipt_id AND rr.source_id=rs.id
              AND rr.household_id=:home AND rs.household_id=:home
        """), {"store_code": store_code, "receipt_id": receipt_id, "home": home})
        conn.execute(text("""
            UPDATE receipt_table_lines
            SET matched_article_id=:article_id,
                matched_global_product_id=NULL,
                article_match_status='matched',
                line_role='product', inventory_eligible=TRUE, barcode=:barcode
            WHERE receipt_table_id=:receipt_id
        """), {
            "article_id": article_id, "barcode": barcode,
            "receipt_id": receipt_id,
        })

    manual_event = _id()
    conn.execute(text("""
        INSERT INTO inventory_events (
            id, household_id, article_id, household_article_id,
            article_name, location_id, location_label,
            event_type, quantity, old_quantity, new_quantity,
            source, note, purchase_date, effective_at, recorded_at,
            effective_at_precision, event_priority, created_at
        ) VALUES (
            :id,:home,:article_id,:article_id,
            'PR732 protected',NULL,NULL,
            'purchase',1,0,1,'ci_manual_adjustment','preserve',
            :day,:moment,CURRENT_TIMESTAMP,'date',10,CURRENT_TIMESTAMP
        )
    """), {
        "id": manual_event, "home": home, "article_id": manual,
        "day": cutoff.isoformat(),
        "moment": cutoff.isoformat() + "T00:00:00+00:00",
    })
    first = refresh_automatic_historical_stock(conn, household_id=home)
    assert first["status"] == "applied", first
    assert first["canonical_repair"]["merged"] == 1, first
    assert first["canonical_repair"]["blocked"] >= 1, first

    active = conn.execute(text("""
        SELECT id FROM household_articles
        WHERE household_id=:home AND id IN (:winner,:duplicate)
          AND COALESCE(status,'active')='active'
    """), {"home": home, "winner": winner, "duplicate": duplicate}).scalars().all()
    assert [str(x) for x in active] == [winner], active
    for receipt_id in receipt_ids[:2]:
        matched = conn.execute(text("""
            SELECT matched_article_id FROM receipt_table_lines
            WHERE receipt_table_id=:receipt_id
        """), {"receipt_id": receipt_id}).scalar_one()
        assert str(matched) == winner, matched

    cadence = read_historical_household_purchase_cadence(
        conn, household_id=home, household_article_id=winner,
    )
    assert cadence["purchase_day_count"] == 2, cadence
    assert cadence["average_repurchase_interval_days"] == 15.0, cadence
    assert conn.execute(text("""
        SELECT COALESCE(SUM(aantal),0) FROM inventory
        WHERE household_id=:home AND household_article_id=:winner
    """), {"home": home, "winner": winner}).scalar_one() == 1
    assert conn.execute(text("""
        SELECT COUNT(*) FROM household_articles
        WHERE household_id=:home AND id IN (:protected,:manual)
          AND COALESCE(status,'active')='active'
    """), {"home": home, "protected": protected, "manual": manual}).scalar_one() == 2
    assert conn.execute(text("""
        SELECT COUNT(*) FROM inventory_events
        WHERE id=:id AND household_id=:home AND household_article_id=:manual
    """), {"id": manual_event, "home": home, "manual": manual}).scalar_one() == 1
    assert conn.execute(text("""
        SELECT COUNT(*) FROM household_articles
        WHERE household_id=:home AND id=:id AND status='active'
    """), {"home": other_home, "id": foreign_id}).scalar_one() == 1
    assert conn.execute(text("""
        SELECT setting_value FROM household_settings
        WHERE household_id=:home AND setting_key='almost_out_prediction_days'
    """), {"home": home}).scalar_one() == "100"
    assert conn.execute(text("""
        SELECT setting_value FROM household_settings
        WHERE household_id=:home AND setting_key='almost_out_prediction_enabled'
    """), {"home": home}).scalar_one() == "true"
    # Check the real Bijna op production evaluator, not a synthetic forecast.
    from app.main import build_almost_out_items
    near = build_almost_out_items(conn, home)
    assert winner in {str(item["household_article_id"]) for item in near}, near
    print("PR732_POSTGRESQL_100_DAY_BIJNA_OP_GREEN")

    before = conn.execute(text("""
        SELECT COUNT(*) FROM inventory_events WHERE household_id=:home
    """), {"home": home}).scalar_one()
    repeated = refresh_automatic_historical_stock(conn, household_id=home)
    assert repeated["canonical_repair"]["merged"] == 0, repeated
    assert repeated["created"] == repeated["revised"] == 0, repeated
    assert conn.execute(text("""
        SELECT COUNT(*) FROM inventory_events WHERE household_id=:home
    """), {"home": home}).scalar_one() == before
    print("PR732_POSTGRESQL_VERIFIED_GTIN_RECOVERY_GREEN")



def main() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Deze DML-test mag uitsluitend in de geïsoleerde GitHub CI draaien")
    if os.environ.get("MIGRATION_DATABASE_URL"):
        raise RuntimeError("DML-only toets mag geen migratiecredentials ontvangen")
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url or make_url(raw_url).get_backend_name() != "postgresql":
        raise RuntimeError("Geïsoleerde PostgreSQL-runtime is verplicht")

    # The canonical PostgreSQL CI installs psycopg v3, not legacy psycopg2.
    # Convert only the SQLAlchemy driver token; preserve host, role and db.
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(url, future=True)
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

                # Exercise the *registered production process endpoint* using
                # the same real PostgreSQL transaction as the fixture. An
                # authorized caller must be stopped before any inventory
                # mutation, even when they bypass the ordinary list UI.
                main = importlib.import_module("app.main")
                for _ in range(100):
                    if getattr(
                        main.app.state,
                        "purchase_import_location_policy_patch_installed",
                        False,
                    ):
                        break
                    time.sleep(0.02)
                else:
                    raise AssertionError("Production inventory route patch not installed")
                process_path = "/api/purchase-import-batches/{batch_id}/process"
                registered = [
                    route for route in main.app.routes
                    if getattr(route, "path", "") == process_path
                       and "POST" in (getattr(route, "methods", set()) or set())
                ]
                assert len(registered) == 1
                assert registered[0].endpoint is main.process_purchase_import_batch

                class _TransactionEngine:
                    def begin(self):
                        return nullcontext(conn)

                with (
                    patch.object(main, "engine", _TransactionEngine()),
                    patch.object(
                        main, "require_household_context",
                        return_value={
                            "active_household_id": new_household,
                            "display_role": "admin",
                        },
                    ),
                ):
                    try:
                        main.process_purchase_import_batch(
                            batch_id,
                            main.ProcessBatchRequest(
                                mode="ready_only", processed_by="ci",
                            ),
                            "ci-authorization",
                        )
                    except HTTPException as exc:
                        assert exc.status_code == 409
                    else:
                        raise AssertionError(
                            "Production batch endpoint accepted historical receipt"
                        )
                print("RECEIPT_HISTORY_POSTGRESQL_PRODUCTION_ROUTE_GUARD_GREEN")

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

                _prove_historical_workflows(
                    conn, main=main, household_id=new_household,
                    provider_id=provider, connection_id=connection,
                    cutover=first_current,
                )

                # PR2: real PostgreSQL, same isolated rollback transaction.
                # Only fully owned household-article links and canonical
                # product semantics may become read-only learning candidates.
                from app.services.receipt_historical_learning_service import (
                    load_historical_learning,
                )
                from app.api.kassa_pagination_routes import list_historical_kassa_learning
                article_id = main.ensure_household_article(
                    conn, new_household, "Historische CI koffiepads",
                )
                for index, age_days in enumerate((100, 65, 30, 2)):
                    candidate_receipt_id, _ = _seed_receipt(
                        conn, household_id=new_household,
                        provider_id=provider, connection_id=connection,
                        store=("Albert Heijn", "Lidl", "Jumbo", "Albert Heijn")[index],
                        purchase_date=first_current - timedelta(days=age_days),
                        with_line=True,
                    )
                    conn.execute(text("""
                        UPDATE receipt_table_lines
                           SET line_role = 'product', inventory_eligible = 1,
                               matched_article_id = :article_id,
                               article_match_status = 'matched'
                         WHERE receipt_table_id = :receipt_id
                    """), {"article_id": article_id, "receipt_id": candidate_receipt_id})
                learning = load_historical_learning(
                    conn, household_id=new_household, page=1, page_size=10,
                )
                assert learning["total"] == 1, learning
                candidate = learning["items"][0]
                assert candidate["key"] == "article:" + article_id, candidate
                assert candidate["estimate_status"] == "indicative_unconfirmed", candidate
                assert candidate["requires_confirmation"] is True, candidate
                assert learning["writes_inventory"] is False, learning
                assert candidate["source_receipt_count"] == 4, candidate
                assert load_historical_learning(
                    conn, household_id=other_household,
                )["status"] == "legacy_not_enabled"

                class _ReadEngine:
                    def connect(self):
                        return nullcontext(conn)

                # Test the actual HTTP route handler, including authorized
                # household resolution and the absence of any DML side effect.
                with (
                    patch("app.api.kassa_pagination_routes.engine", _ReadEngine()),
                    patch.object(main, "resolve_authorized_household_id",
                                 return_value=new_household),
                ):
                    exposed = list_historical_kassa_learning(
                        householdId=new_household, page=1, page_size=10,
                        authorization="ci-authorized",
                    )
                assert exposed["items"] == learning["items"], exposed
                assert any(
                    getattr(route, "path", "") == "/api/kassa/historical-learning-page"
                    and "GET" in (getattr(route, "methods", set()) or set())
                    for route in main.app.routes
                ), "Read-only PR2 endpoint not registered"
                print("RECEIPT_HISTORY_POSTGRESQL_LEARNING_READONLY_GREEN")

                # This proof uses real, canonical storage but does not invoke
                # the stock API: it establishes that no stock is synthesized
                # by history activation, retention or validation alone.
                for table in ("inventory", "inventory_events"):
                    count = conn.execute(text(
                        f"SELECT COUNT(*) FROM {table} WHERE household_id=:household_id"
                    ), {"household_id": new_household}).scalar_one()
                    assert count == 0, f"Historical receipts mutated {table}"
                print("RECEIPT_HISTORY_POSTGRESQL_ZERO_STOCK_MUTATION_GREEN")

                # PR3: the automatic projection is invoked explicitly inside
                # this *isolated CI rollback transaction*, never in a user's
                # existing local or server database. No approval UI exists.
                from app.services.historical_household_stock_source import (
                    load_automatic_historical_stock,
                )
                from app.services.historical_household_stock_writer import (
                    refresh_automatic_historical_stock,
                )
                from app.services.historical_household_purchase_cadence import (
                    read_historical_household_purchase_cadence,
                )
                conn.execute(text("""
                    UPDATE household_articles SET consumable = 1
                    WHERE household_id=:household_id AND id=:article_id
                """), {"household_id": new_household, "article_id": article_id})
                conn.execute(text("""
                    INSERT INTO household_settings (
                        id, household_id, setting_key, setting_value, updated_at
                    ) VALUES (
                        :id, :household_id, 'consumable_auto_deduction_mode',
                        'consume_all_existing_before_purchase', CURRENT_TIMESTAMP
                    ) ON CONFLICT(household_id, setting_key) DO UPDATE
                    SET setting_value=excluded.setting_value
                """), {"id": _id(), "household_id": new_household})
                calculated = load_automatic_historical_stock(
                    conn, household_id=new_household,
                )
                assert calculated["status"] == "calculated", calculated
                assert calculated["quantities"] == {article_id: 1}, calculated
                assert calculated["purchase_cadences"][article_id]["purchase_day_count"] == 4
                assert calculated["purchase_cadences"][article_id]["average_repurchase_interval_days"] > 0
                before_count = conn.execute(text("""
                    SELECT COUNT(*) FROM inventory
                    WHERE household_id=:household_id
                """), {"household_id": new_household}).scalar_one()
                assert before_count == 0
                first_applied = refresh_automatic_historical_stock(
                    conn, household_id=new_household,
                )
                assert first_applied["status"] == "applied", first_applied
                assert first_applied["created"] == 1, first_applied
                assert first_applied["cadences_written"] == 1, first_applied
                stored = conn.execute(text("""
                    SELECT aantal, space_id, sublocation_id FROM inventory
                    WHERE household_id=:household_id AND household_article_id=:article_id
                """), {"household_id": new_household, "article_id": article_id}).mappings().all()
                assert len(stored) == 1 and int(stored[0]["aantal"]) == 1, stored
                assert stored[0]["space_id"] is None and stored[0]["sublocation_id"] is None
                source_event = conn.execute(text("""
                    SELECT event_type, source, quantity FROM inventory_events
                    WHERE household_id=:household_id AND household_article_id=:article_id
                """), {"household_id": new_household, "article_id": article_id}).mappings().all()
                assert len(source_event) == 1 and source_event[0]["source"] == "historical_auto_stock", source_event
                assert source_event[0]["event_type"] == "baseline" and int(source_event[0]["quantity"]) == 1
                cadence = read_historical_household_purchase_cadence(
                    conn, household_id=new_household, household_article_id=article_id,
                )
                assert cadence and cadence["purchase_day_count"] == 4
                assert read_historical_household_purchase_cadence(
                    conn, household_id=other_household, household_article_id=article_id,
                ) is None
                second = refresh_automatic_historical_stock(
                    conn, household_id=new_household,
                )
                assert second["created"] == second["revised"] == second["cadences_written"] == 0, second
                for table in ("inventory", "inventory_events",
                              "household_historical_auto_stock_baselines",
                              "household_historical_purchase_cadences"):
                    count = conn.execute(text(
                        f"SELECT COUNT(*) FROM {table} WHERE household_id=:household_id"
                    ), {"household_id": new_household}).scalar_one()
                    assert count == 1, (table, count)
                print("RECEIPT_HISTORY_POSTGRESQL_AUTO_STOCK_CADENCE_GREEN")

                # PR3: one historical purchase followed by one *current*
                # purchase suffices for a saved cadence; subsequent purchases
                # recompute it without changing any established stock.
                # This savepoint rolls back before the outer CI rollback.
                with conn.begin_nested() as repeat_savepoint:
                    repeat_article_id = main.ensure_household_article(
                        conn, new_household, "Historische CI eerste herhaalaankoop",
                    )
                    conn.execute(text("""
                        UPDATE household_articles
                        SET consumable = 1
                        WHERE household_id=:household_id AND id=:article_id
                    """), {"household_id": new_household, "article_id": repeat_article_id})
                    historic_day = first_current - timedelta(days=25)
                    historic_id, _ = _seed_receipt(
                        conn, household_id=new_household,
                        provider_id=provider, connection_id=connection,
                        store="Lidl", purchase_date=historic_day,
                        approved=False, with_line=True,
                    )
                    conn.execute(text("""
                        UPDATE receipt_table_lines
                        SET line_role='product', inventory_eligible=1,
                            matched_article_id=:article_id,
                            article_match_status='matched'
                        WHERE receipt_table_id=:receipt_id
                    """), {"article_id": repeat_article_id, "receipt_id": historic_id})
                    initial = load_automatic_historical_stock(
                        conn, household_id=new_household,
                    )
                    assert repeat_article_id in initial["purchase_days_by_article"]
                    assert repeat_article_id not in initial["purchase_cadences"]

                    def add_current_purchase(days_after, label):
                        purchase_day = first_current + timedelta(days=days_after)
                        conn.execute(text("""
                            INSERT INTO inventory_events (
                                id, household_id, article_id, household_article_id,
                                article_name, location_id, location_label,
                                event_type, quantity, old_quantity, new_quantity,
                                source, note, purchase_date,
                                effective_at, recorded_at,
                                effective_at_precision, event_priority, created_at
                            ) VALUES (
                                :id, :household_id, :article_id, :article_id,
                                'Historische CI eerste herhaalaankoop', NULL, NULL,
                                'purchase', 1, 0, 1, 'ci_purchase', :label,
                                :purchase_date, :effective_at, CURRENT_TIMESTAMP,
                                'date', 10, CURRENT_TIMESTAMP
                            )
                        """), {
                            "id": _id(), "household_id": new_household,
                            "article_id": repeat_article_id, "label": label,
                            "purchase_date": purchase_day.isoformat(),
                            "effective_at": purchase_day.isoformat() + "T00:00:00+00:00",
                        })

                    add_current_purchase(2, "Eerste herhaalaankoop")
                    first_repeat = refresh_automatic_historical_stock(
                        conn, household_id=new_household,
                    )
                    assert first_repeat["status"] == "applied", first_repeat
                    result = read_historical_household_purchase_cadence(
                        conn, household_id=new_household,
                        household_article_id=repeat_article_id,
                    )
                    assert result is not None, first_repeat
                    assert result["purchase_day_count"] == 2, result
                    assert result["average_repurchase_interval_days"] == 27.0, result
                    # Existing live purchase event proves the new baseline
                    # must not create/overwrite current stock for this article.
                    assert conn.execute(text("""
                        SELECT COUNT(*) FROM household_historical_auto_stock_baselines
                        WHERE household_id=:household_id
                          AND household_article_id=:article_id
                    """), {"household_id": new_household,
                           "article_id": repeat_article_id}).scalar_one() == 0

                    add_current_purchase(12, "Volgende herhaalaankoop")
                    add_current_purchase(12, "Zelfde dag, tweede winkel")
                    second_repeat = refresh_automatic_historical_stock(
                        conn, household_id=new_household,
                    )
                    result = read_historical_household_purchase_cadence(
                        conn, household_id=new_household,
                        household_article_id=repeat_article_id,
                    )
                    assert second_repeat["cadences_written"] >= 1, second_repeat
                    assert result["purchase_day_count"] == 3, result
                    assert result["average_repurchase_interval_days"] == 18.5, result
                    repeat_savepoint.rollback()
                print("RECEIPT_HISTORY_POSTGRESQL_ONE_REPEAT_CADENCE_GREEN")

                # No historical receipts at all: a household still learns
                # after one live repeat, while no initial stock baseline is
                # fabricated from already-processed current purchase events.
                with conn.begin_nested() as current_only_savepoint:
                    current_home = _seed_household(conn)
                    assert activate_cutover_for_new_onboarding(
                        conn, household_id=current_home,
                    )
                    current_cutover = read_household_cutover(conn, current_home)
                    current_article = main.ensure_household_article(
                        conn, current_home, "CI alleen actuele aankopen",
                    )
                    for index, offset in enumerate((1, 15)):
                        day = current_cutover + timedelta(days=offset)
                        conn.execute(text("""
                            INSERT INTO inventory_events (
                                id, household_id, article_id, household_article_id,
                                article_name, location_id, location_label,
                                event_type, quantity, old_quantity, new_quantity,
                                source, note, purchase_date,
                                effective_at, recorded_at,
                                effective_at_precision, event_priority, created_at
                            ) VALUES (
                                :id, :household_id, :article_id, :article_id,
                                'CI alleen actuele aankopen', NULL, NULL,
                                'purchase', 1, 0, 1, 'ci_purchase', :note,
                                :purchase_date, :effective_at, CURRENT_TIMESTAMP,
                                'date', 10, CURRENT_TIMESTAMP
                            )
                        """), {
                            "id": _id(), "household_id": current_home,
                            "article_id": current_article,
                            "note": "CI live " + str(index),
                            "purchase_date": day.isoformat(),
                            "effective_at": day.isoformat() + "T00:00:00+00:00",
                        })
                    current_report = refresh_automatic_historical_stock(
                        conn, household_id=current_home,
                    )
                    assert current_report["status"] == "no_trusted_matches", current_report
                    assert current_report["cadences_written"] == 1, current_report
                    current_interval = read_historical_household_purchase_cadence(
                        conn, household_id=current_home,
                        household_article_id=current_article,
                    )
                    assert current_interval["purchase_day_count"] == 2, current_interval
                    assert current_interval["average_repurchase_interval_days"] == 14.0, current_interval
                    for table in ("household_historical_auto_stock_baselines", "inventory"):
                        assert conn.execute(text(
                            f"SELECT COUNT(*) FROM {table} WHERE household_id=:household_id"
                        ), {"household_id": current_home}).scalar_one() == 0, table
                    current_only_savepoint.rollback()
                print("RECEIPT_HISTORY_POSTGRESQL_CURRENT_ONLY_CADENCE_GREEN")

                with conn.begin_nested() as pr732_savepoint:
                    _prove_pr732_historical_identity_recovery(
                        conn, household_id=new_household,
                        other_household=other_household,
                        provider_id=provider, connection_id=connection,
                        cutover=first_current,
                    )
                    pr732_savepoint.rollback()
                with conn.begin_nested() as gtin_savepoint:
                    _prove_pr732_verified_gtin_recovery(conn, cutoff=first_current)
                    gtin_savepoint.rollback()



            finally:
                tx.rollback()
    finally:
        engine.dispose()
    print("RECEIPT_HISTORY_POSTGRESQL_TRANSACTION_ROLLBACK_GREEN")


if __name__ == "__main__":
    main()
