from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / "backend" / "app" / "services" / "retailer_receipt_import_service.py"


def test_retailer_duplicate_refresh_is_limited_to_safe_kassa_receipts() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8")
    start = source.index("def _refresh_existing_retailer_receipt_if_safe(")
    end = source.index("def import_retailer_receipt(", start)
    block = source[start:end]

    assert 'row.get("approved_at") is not None' in block
    assert 'workflow_state not in {"active", "returned_to_kassa"}' in block
    assert "has_user_line_edits" in block
    assert 'str(row.get("source_id") or "") != str(source_id or "")' in block
    assert 'str(row.get("original_filename") or "") != filename' in block
    assert "reparse_receipt(" in block
