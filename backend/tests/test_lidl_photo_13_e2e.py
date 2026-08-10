from __future__ import annotations

import hashlib
import importlib
import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy import text

EXPECTED_SHA256 = "52a645b56b90037c34a54e61afc594c591874d5b8f9e5e3632332a80ecd5013b"
HOUSEHOLD_ID = "0"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lidl_photo_13.jpeg"


def _load_main(database_path: Path, storage_root: Path):
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    os.environ["RECEIPT_STORAGE_ROOT"] = str(storage_root)
    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    for name in [n for n in list(sys.modules) if n == "app" or n.startswith("app.")]:
        del sys.modules[name]
    return importlib.import_module("app.main")


def _initialize_schema(main) -> None:
    schema_functions = [
        (name, value)
        for name, value in vars(main).items()
        if name.startswith("ensure_release_") and name.endswith("_schema") and callable(value)
    ]
    for _, function in sorted(schema_functions, key=lambda item: item[0]):
        function()


def run() -> dict:
    assert FIXTURE.exists(), f"Fixture ontbreekt: {FIXTURE}"
    fixture_bytes = FIXTURE.read_bytes()
    actual_sha = hashlib.sha256(fixture_bytes).hexdigest()
    assert actual_sha == EXPECTED_SHA256, (
        f"Verkeerde Lidl-13 fixture. Verwacht {EXPECTED_SHA256}, gevonden {actual_sha}"
    )

    with tempfile.TemporaryDirectory(prefix="rezzerv-lidl13-e2e-") as tmp:
        root = Path(tmp)
        main = _load_main(root / "rezzerv.sqlite", root / "receipts")
        _initialize_schema(main)

        result = main.import_uploaded_receipt_payload(
            household_id=HOUSEHOLD_ID,
            filename="lidl_photo_13.jpeg",
            file_bytes=fixture_bytes,
            source_id=None,
            mime_type="image/jpeg",
            reject_non_receipt=False,
            create_failed_receipt_table=False,
            include_debug=True,
        )

        receipt_table_id = str(result.get("receipt_table_id") or "").strip()
        raw_receipt_id = str(result.get("raw_receipt_id") or "").strip()
        parsed = result.get("parsed") if isinstance(result.get("parsed"), dict) else {}

        assert raw_receipt_id, f"Geen raw_receipt_id in importresultaat: {result}"
        assert receipt_table_id, (
            "Lidl foto 13 kreeg geen receipt_table_id via de normale productie-import; "
            f"resultaat={result}"
        )

        with main.engine.begin() as conn:
            persisted = conn.execute(
                text(
                    "SELECT id, household_id, store_name, purchase_at, total_amount, parse_status "
                    "FROM receipt_tables WHERE id = :id LIMIT 1"
                ),
                {"id": receipt_table_id},
            ).mappings().first()
        assert persisted is not None, f"receipt_tables-record ontbreekt voor {receipt_table_id}"
        assert str(persisted.get("household_id") or "") == HOUSEHOLD_ID

        # Test de productie-listprojectie zonder het autorisatiemodel zelf onderdeel van deze receipt-test te maken.
        original_resolver = main.resolve_authorized_household_id
        try:
            main.resolve_authorized_household_id = lambda authorization, household_id, require_authorization=True: HOUSEHOLD_ID
            listing = main.list_receipts(householdId=HOUSEHOLD_ID, authorization="Bearer e2e")
        finally:
            main.resolve_authorized_household_id = original_resolver

        items = listing.get("items") if isinstance(listing, dict) else None
        assert isinstance(items, list), f"Onverwachte /api/receipts-projectie: {listing}"
        listed_ids = {
            str(item.get("id") or item.get("receipt_table_id") or "")
            for item in items
            if isinstance(item, dict)
        }
        assert receipt_table_id in listed_ids, (
            f"Bon {receipt_table_id} staat wel in receipt_tables maar niet in de Kassa-lijst; ids={sorted(listed_ids)}"
        )

        return {
            "status": "passed",
            "fixture_sha256": actual_sha,
            "raw_receipt_id": raw_receipt_id,
            "receipt_table_id": receipt_table_id,
            "store_name": persisted.get("store_name") or parsed.get("store_name"),
            "purchase_at": str(persisted.get("purchase_at") or parsed.get("purchase_at") or ""),
            "total_amount": str(persisted.get("total_amount") or parsed.get("total_amount") or ""),
            "parse_status": str(persisted.get("parse_status") or parsed.get("parse_status") or ""),
            "listed_in_kassa": True,
        }


if __name__ == "__main__":
    result = run()
    print(result)
