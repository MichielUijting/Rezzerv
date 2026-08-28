from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, text

from app.integrations.receipt_scanners.adapters.fake_test_provider import FakeScannerProvider
from app.integrations.receipt_scanners.gateway import ReceiptScannerGateway
from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.integrations.receipt_scanners.registry import ProviderRegistry
from app.integrations.receipt_scanners.schemas.canonical_receipt_v1 import CanonicalReceiptV1
from app.integrations.receipt_scanners.schemas.scan_request_v1 import ScanRequestV1
from app.services.temporal_inventory_service import (
    TemporalInventoryEvent,
    ensure_temporal_inventory_schema,
    insert_temporal_event,
    ordered_events,
    reconcile_inventory_total,
)


HOUSEHOLD_ID = "po-temporal-household"
ARTICLE_ID = "po-halfvolle-melk"
ARTICLE_NAME = "Halfvolle melk 1L"


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                article_id TEXT NOT NULL,
                household_article_id TEXT,
                article_name TEXT,
                location_id TEXT,
                location_label TEXT,
                event_type TEXT NOT NULL,
                quantity NUMERIC NOT NULL,
                old_quantity NUMERIC NOT NULL DEFAULT 0,
                new_quantity NUMERIC NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'system',
                note TEXT,
                purchase_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                effective_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                effective_at_precision TEXT NOT NULL DEFAULT 'datetime',
                event_priority INTEGER NOT NULL DEFAULT 100,
                source_reference TEXT,
                source_line_id INTEGER,
                replayed_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE INDEX idx_inventory_events_temporal_order
            ON inventory_events (
                household_id, household_article_id, effective_at, event_priority, id
            )
        """))
        conn.execute(text("""
            CREATE INDEX idx_inventory_events_source_reference
            ON inventory_events (source, source_reference, source_line_id)
        """))
        conn.execute(text("""
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                household_article_id TEXT NOT NULL,
                aantal NUMERIC NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                updated_at TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO inventory (id, household_id, household_article_id, aantal, status)
            VALUES ('inv-po-melk', :household_id, :article_id, 0, 'active')
        """), {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID})
        ensure_temporal_inventory_schema(conn)
    return engine


def _request(scan_id: str, marker: str) -> ScanRequestV1:
    return ScanRequestV1.from_bytes(
        scan_id=scan_id,
        file_bytes=f"test receipt {marker}".encode("utf-8"),
        filename=f"{marker}.jpg",
        mime_type="image/jpeg",
    )


def _receipt(
    request: ScanRequestV1,
    *,
    purchase_date: str,
    purchase_time: str,
    quantity: int,
    receipt_number: str,
) -> CanonicalReceiptV1:
    unit_price = Decimal("1.39")
    total = unit_price * Decimal(quantity)
    return CanonicalReceiptV1.model_validate({
        "schema_version": "1.0",
        "scan_id": request.scan_id,
        "provider": {
            "code": "fake-test",
            "result_id": f"result-{receipt_number}",
            "model_version": "po-temporal-v1",
        },
        "status": "completed",
        "document": {
            "sha256": request.document.sha256,
            "mime_type": request.document.mime_type,
            "page_count": 1,
        },
        "receipt": {
            "store": {"name": "PO Testwinkel", "branch_name": "Driel"},
            "transaction": {
                "purchase_date": purchase_date,
                "purchase_time": purchase_time,
                "receipt_number": receipt_number,
                "currency": "EUR",
            },
            "totals": {"grand_total": str(total)},
            "lines": [{
                "line_number": 1,
                "line_type": "product",
                "raw_text": f"{quantity} HALF VOLLE MELK 1L {total}",
                "description": ARTICLE_NAME,
                "quantity": str(quantity),
                "unit": "piece",
                "unit_price": str(unit_price),
                "line_total": str(total),
                "identifiers": {"gtin": "8710000000001"},
                "confidence": {
                    "description": 0.99,
                    "quantity": 0.99,
                    "unit_price": 0.99,
                    "line_total": 0.99,
                    "identifier": 0.99,
                },
            }],
            "warnings": [],
        },
        "quality": {"overall_confidence": 0.99, "requires_review": False},
    })


def _persist_scanned_purchase(conn, canonical: CanonicalReceiptV1, receipt_reference: str) -> str:
    parsed = canonical_to_receipt_parse_result(canonical)
    assert parsed.purchase_at is not None
    assert len(parsed.lines) == 1
    quantity = Decimal(str(parsed.lines[0]["quantity"] or 0))
    insert_temporal_event(
        conn,
        TemporalInventoryEvent(
            household_id=HOUSEHOLD_ID,
            household_article_id=ARTICLE_ID,
            article_name=ARTICLE_NAME,
            event_type="purchase",
            quantity=quantity,
            effective_at=parsed.purchase_at,
            effective_at_precision="datetime",
            source="receipt",
            source_reference=f"receipt:{receipt_reference}",
            source_line_id="1",
        ),
    )
    reconcile_inventory_total(
        conn,
        household_id=HOUSEHOLD_ID,
        household_article_id=ARTICLE_ID,
        preferred_inventory_id="inv-po-melk",
    )
    return parsed.purchase_at


def test_recent_receipt_then_consumption_then_older_receipt_uses_receipt_time_not_scan_order():
    """PO case: scanner ingestion order must not determine inventory chronology."""
    recent_request = _request("rscan-po-recent", "recent")
    old_request = _request("rscan-po-old", "old")

    recent_result = _receipt(
        recent_request,
        purchase_date="2026-08-06",
        purchase_time="12:00:00",
        quantity=2,
        receipt_number="B-0608",
    )
    old_result = _receipt(
        old_request,
        purchase_date="2026-08-04",
        purchase_time="18:21:37",
        quantity=3,
        receipt_number="A-0408",
    )

    provider = FakeScannerProvider([recent_result, old_result])
    gateway = ReceiptScannerGateway(
        ProviderRegistry([provider], active_provider_code="fake-test"),
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    engine = _engine()
    with engine.begin() as conn:
        # 1) The newer receipt is scanned first through the Release-A provider boundary.
        scanned_recent = gateway.scan(recent_request)
        recent_purchase_at = _persist_scanned_purchase(conn, scanned_recent, "B-0608")
        assert recent_purchase_at == "2026-08-06T12:00:00"

        # 2) One unit is consumed after that purchase.
        insert_temporal_event(
            conn,
            TemporalInventoryEvent(
                household_id=HOUSEHOLD_ID,
                household_article_id=ARTICLE_ID,
                article_name=ARTICLE_NAME,
                event_type="consume",
                quantity=Decimal("1"),
                effective_at="2026-08-07T08:00:00",
                source="manual",
                source_reference="consume:po-0708",
            ),
        )
        reconcile_inventory_total(
            conn,
            household_id=HOUSEHOLD_ID,
            household_article_id=ARTICLE_ID,
            preferred_inventory_id="inv-po-melk",
        )

        # 3) Only now is the older receipt scanned, again through the same provider boundary.
        scanned_old = gateway.scan(old_request)
        old_purchase_at = _persist_scanned_purchase(conn, scanned_old, "A-0408")
        assert old_purchase_at == "2026-08-04T18:21:37"

        history = ordered_events(
            conn,
            household_id=HOUSEHOLD_ID,
            household_article_id=ARTICLE_ID,
        )
        assert [row["effective_at"] for row in history] == [
            "2026-08-04T18:21:37+00:00",
            "2026-08-06T12:00:00+00:00",
            "2026-08-07T08:00:00+00:00",
        ]
        assert [str(row["source_reference"]) for row in history] == [
            "receipt:A-0408",
            "receipt:B-0608",
            "consume:po-0708",
        ]

        balances = conn.execute(text("""
            SELECT source_reference, old_quantity, new_quantity
            FROM inventory_events
            WHERE household_id = :household_id
              AND household_article_id = :article_id
            ORDER BY datetime(effective_at), event_priority, id
        """), {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID}).mappings().all()
        assert [(row["source_reference"], float(row["old_quantity"]), float(row["new_quantity"])) for row in balances] == [
            ("receipt:A-0408", 0.0, 3.0),
            ("receipt:B-0608", 3.0, 5.0),
            ("consume:po-0708", 5.0, 4.0),
        ]

        current_stock = conn.execute(text("""
            SELECT aantal
            FROM inventory
            WHERE household_id = :household_id
              AND household_article_id = :article_id
        """), {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID}).scalar_one()
        assert float(current_stock) == 4.0
