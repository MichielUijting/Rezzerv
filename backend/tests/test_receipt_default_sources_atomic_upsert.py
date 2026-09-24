from __future__ import annotations

import inspect

from app.services.receipt_service import ensure_default_receipt_sources


def test_default_receipt_sources_use_atomic_postgresql_upsert():
    source = inspect.getsource(ensure_default_receipt_sources)

    assert "ON CONFLICT (id) DO UPDATE" in source
    assert "EXCLUDED.household_id" in source
    assert "EXCLUDED.type" in source
    assert "EXCLUDED.label" in source
    assert "EXCLUDED.source_path" in source
    assert "EXCLUDED.is_active" in source
    assert "SELECT id FROM receipt_sources WHERE id = :id LIMIT 1" not in source
    assert "'id': f'{household_id}-local-folder'" in source
    assert "'id': f'{household_id}-scan-folder'" in source
