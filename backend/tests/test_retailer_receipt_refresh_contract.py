from __future__ import annotations

import inspect

from app.services import retailer_receipt_import_service


def test_retailer_duplicate_refresh_is_limited_to_safe_kassa_receipts() -> None:
    source = inspect.getsource(
        retailer_receipt_import_service._refresh_existing_retailer_receipt_if_safe
    )

    assert 'row.get("approved_at") is not None' in source
    assert 'workflow_state not in {"active", "returned_to_kassa"}' in source
    assert 'has_user_line_edits' in source
    assert 'str(row.get("source_id") or "") != str(source_id or "")' in source
    assert 'str(row.get("original_filename") or "") != filename' in source
    assert "reparse_receipt(" in source
