from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_product_candidate_store import (
    ensure_external_product_candidates_schema,
    list_external_receipt_items,
)

CANDIDATE_ID = "po-v0112105-recognition-candidate"
CANDIDATE_NAME = "PO-test Herkenning v01.12.105"
SOURCE_NAME = "po_local_fixture"
SOURCE_CODE = "po:v01.12.105:external-recognition"
BASELINE_PATH = Path("/app/data/po-v0112105-recognition-baseline.json")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _table_exists(conn, table_name: str) -> bool:
    return (
        conn.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = :table_name"
            ),
            {"table_name": table_name},
        ).first()
        is not None
    )


def _count(conn, table_name: str) -> int:
    if not _table_exists(conn, table_name):
        return 0
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)


def _baseline_counts(conn) -> dict[str, int]:
    return {
        "global_products": _count(conn, "global_products"),
        "product_identities": _count(conn, "product_identities"),
        "household_articles": _count(conn, "household_articles"),
        "inventory_events": _count(conn, "inventory_events"),
    }


def _choose_receipt_item() -> dict[str, Any]:
    payload = list_external_receipt_items(limit=500)
    items = [item for item in payload.get("items") or [] if isinstance(item, dict)]

    candidates: list[dict[str, Any]] = []
    for item in items:
        purchase_import_line_id = _text(item.get("purchase_import_line_id"))
        receipt_line_text = _text(item.get("receipt_line_text"))
        retailer_code = _text(item.get("retailer_code")).lower()
        global_product_id = _text(item.get("global_product_id"))
        if not purchase_import_line_id or not receipt_line_text:
            continue
        if retailer_code in {"", "-", "onbekend", "unknown", "import"}:
            continue
        if global_product_id:
            continue
        candidates.append(item)

    if not candidates:
        raise RuntimeError(
            "Geen ongekoppelde purchase_import_line met bekende winkelketen gevonden "
            "in de geisoleerde databasekopie."
        )

    candidates.sort(
        key=lambda item: (
            len(item.get("candidates") or []),
            _text(item.get("receipt_line_text")).lower(),
            _text(item.get("purchase_import_line_id")),
        )
    )
    return candidates[0]


def prepare() -> None:
    ensure_external_product_candidates_schema()
    target = _choose_receipt_item()
    purchase_import_line_id = _text(target.get("purchase_import_line_id"))
    receipt_line_text = _text(target.get("receipt_line_text"))
    retailer_code = _text(target.get("retailer_code")).lower()
    context_key = f"purchase-import-line:{purchase_import_line_id}"

    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM external_product_candidates "
                "WHERE id = :candidate_id "
                "OR purchase_import_line_id = :purchase_import_line_id "
                "OR context_key = :context_key"
            ),
            {
                "candidate_id": CANDIDATE_ID,
                "purchase_import_line_id": purchase_import_line_id,
                "context_key": context_key,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO external_product_candidates (
                    id, purchase_import_line_id, context_key, retailer_code,
                    receipt_line_text, candidate_name, candidate_brand,
                    candidate_source_name, candidate_source_product_code,
                    source_name, source_product_code, retailer_article_number,
                    score, status, candidate_status, is_probable,
                    is_user_confirmed, is_external_database_override,
                    created_by, created_at, updated_at, global_product_id
                ) VALUES (
                    :id, :purchase_import_line_id, :context_key, :retailer_code,
                    :receipt_line_text, :candidate_name, :candidate_brand,
                    :source_name, :source_code,
                    :source_name, :source_code, :source_code,
                    0.999, 'probable_candidate', 'probable_candidate', 1,
                    0, 0, 'po_local_fixture', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL
                )
                """
            ),
            {
                "id": CANDIDATE_ID,
                "purchase_import_line_id": purchase_import_line_id,
                "context_key": context_key,
                "retailer_code": retailer_code,
                "receipt_line_text": receipt_line_text,
                "candidate_name": CANDIDATE_NAME,
                "candidate_brand": "Rezzerv PO-test",
                "source_name": SOURCE_NAME,
                "source_code": SOURCE_CODE,
            },
        )
        baseline = _baseline_counts(conn)

    BASELINE_PATH.write_text(
        json.dumps(
            {
                "candidate_id": CANDIDATE_ID,
                "purchase_import_line_id": purchase_import_line_id,
                "receipt_line_text": receipt_line_text,
                "retailer_code": retailer_code,
                "counts": baseline,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "PO_EXTERNAL_RECOGNITION_FIXTURE_GREEN|"
        f"bonartikel={receipt_line_text}|winkel={retailer_code}|"
        f"kandidaat={CANDIDATE_NAME}|bron={SOURCE_NAME}|code={SOURCE_CODE}"
    )


def verify() -> None:
    if not BASELINE_PATH.exists():
        raise RuntimeError(f"Baselinebestand ontbreekt: {BASELINE_PATH}")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    with engine.begin() as conn:
        candidate = conn.execute(
            text(
                """
                SELECT id, status, candidate_status, global_product_id,
                       is_user_confirmed, is_external_database_override
                FROM external_product_candidates
                WHERE id = :candidate_id
                LIMIT 1
                """
            ),
            {"candidate_id": CANDIDATE_ID},
        ).mappings().first()
        if not candidate:
            raise RuntimeError("PO-testkandidaat is verdwenen uit de testdatabase.")

        assert _text(candidate.get("status")).lower() == "external_resolved", candidate
        assert _text(candidate.get("candidate_status")).lower() == "external_resolved", candidate
        assert not _text(candidate.get("global_product_id")), candidate
        assert int(candidate.get("is_user_confirmed") or 0) == 0, candidate
        assert int(candidate.get("is_external_database_override") or 0) == 0, candidate

        current_counts = _baseline_counts(conn)

    expected_counts = {key: int(value) for key, value in (baseline.get("counts") or {}).items()}
    if current_counts != expected_counts:
        raise AssertionError(
            "Bevestigen wijzigde verboden domeintellingen: "
            f"voor={expected_counts}, na={current_counts}"
        )

    print(
        "PO_EXTERNAL_RECOGNITION_VERIFY_GREEN|"
        "status=external_resolved|catalogus_ongewijzigd=1|"
        "mijn_artikel_ongewijzigd=1|voorraad_events_ongewijzigd=1"
    )


def main() -> None:
    action = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if action == "prepare":
        prepare()
        return
    if action == "verify":
        verify()
        return
    raise SystemExit("Gebruik: po_external_recognition_fixture.py prepare|verify")


if __name__ == "__main__":
    main()
