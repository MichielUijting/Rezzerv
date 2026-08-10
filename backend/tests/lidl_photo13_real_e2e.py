"""Real-image regression for the Lidl Arnhem receipt uploaded by the PO.

This is intentionally an end-to-end backend regression. It uses the production
receipt import orchestration and the production receipt list projection. The
fixture is accepted only when its bytes match the PO-provided image exactly.
"""
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
    # Reuse production schema initializers instead of creating a synthetic
    # receipt schema in the regression itself.
    functions = [
        (name, value)
        for name, value in vars(main).items()
        if name.startswith("ensure_release_") and name.endswith("_schema") and callable(value)
    ]
    for _, function in sorted(functions, key=lambda item: item[0]):
        function()
    main.ensure_default_receipt_sources(main.engine, main.RECEIPT_STORAGE_ROOT, HOUSEHOLD_ID)


def run() -> dict:
    assert FIXTURE.is_file(), f"Real Lidl fixture ontbreekt: {FIXTURE}"
    payload = FIXTURE.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    assert digest == EXPECTED_SHA256, (
        "Lidl fixture bytes wijken af van de PO-upload: "
        f"expected={EXPECTED_SHA256} actual={digest}"
    )

    with tempfile.TemporaryDirectory(prefix="rezzerv_lidl13_e2e_") as tmp:
        root = Path(tmp)
        main = _load_main(root / "rezzerv.sqlite", root / "receipts")
        _initialize_schema(main)

        # Deliberately disable the 'persist failed upload anyway' fallback.
        # This regression must prove that the real Lidl image itself reaches
        # the normal recognized-receipt path after the scanner-boundary fix.
        result = main.import_uploaded_receipt_payload(
            household_id=HOUSEHOLD_ID,
            filename="Lidl foto 13.jpeg",
            file_bytes=payload,
            mime_type="image/jpeg",
            reject_non_receipt=False,
            create_failed_receipt_table=False,
            include_debug=True,
        )

        receipt_id = str(result.get("receipt_table_id") or "").strip()
        parsed = result.get("parsed") if isinstance(result.get("parsed"), dict) else {}
        diagnostics = {
            "fixture_sha256": digest,
            "receipt_table_id": receipt_id,
            "is_receipt": result.get("is_receipt", parsed.get("is_receipt")),
            "parse_status": result.get("parse_status", parsed.get("parse_status")),
            "store_name": parsed.get("store_name") or result.get("store_name"),
            "purchase_at": parsed.get("purchase_at") or result.get("purchase_at"),
            "total_amount": parsed.get("total_amount") or result.get("total_amount"),
            "line_count": len(parsed.get("lines") or result.get("lines") or []),
        }
        print("LIDL_PHOTO_13_IMPORT_DIAGNOSTICS", diagnostics)

        assert receipt_id, (
            "Lidl foto 13 kreeg geen receipt_table_id; volledige importdiagnose: "
            f"{diagnostics}"
        )

        with main.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT id, household_id, store_name, purchase_at, total_amount, parse_status "
                    "FROM receipt_tables WHERE id = :id AND household_id = :household_id LIMIT 1"
                ),
                {"id": receipt_id, "household_id": HOUSEHOLD_ID},
            ).mappings().first()
        assert row is not None, f"receipt_tables mist aangemaakte bon {receipt_id}"

        # Exercise the real Kassa list projection, while replacing only the
        # authorization lookup with the already established household 0 test
        # context. No list filtering/projection code is mocked.
        original_resolver = main.resolve_authorized_household_id
        try:
            main.resolve_authorized_household_id = lambda *args, **kwargs: HOUSEHOLD_ID
            listing = main.list_receipts(householdId=HOUSEHOLD_ID, authorization="e2e-session")
        finally:
            main.resolve_authorized_household_id = original_resolver

        items = listing.get("items") if isinstance(listing, dict) else None
        assert isinstance(items, list), f"/api/receipts-projectie gaf geen items-lijst: {listing!r}"
        listed_ids = {str(item.get("id") or "") for item in items if isinstance(item, dict)}
        assert receipt_id in listed_ids, (
            f"Bon {receipt_id} bestaat in receipt_tables maar ontbreekt in de Kassa-lijst"
        )

        diagnostics["persisted"] = True
        diagnostics["listed_in_kassa"] = True
        print("LIDL_PHOTO_13_REAL_E2E=PASS", diagnostics)
        return diagnostics


if __name__ == "__main__":
    run()
