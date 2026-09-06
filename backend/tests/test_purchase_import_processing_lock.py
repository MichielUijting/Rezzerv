from pathlib import Path
from types import SimpleNamespace

from app.services.unpacking_household_object_guard import (
    acquire_purchase_import_processing_lock,
    install_unpacking_household_object_guard,
)


class RecordingConnection:
    def __init__(self, dialect_name: str):
        self.dialect = SimpleNamespace(name=dialect_name)
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), dict(params or {})))
        return None


def test_postgresql_process_request_acquires_batch_advisory_lock():
    conn = RecordingConnection("postgresql")

    locked = acquire_purchase_import_processing_lock(
        conn,
        "POST",
        "/api/purchase-import-batches/batch-123/process",
    )

    assert locked is True
    assert len(conn.calls) == 1
    statement, params = conn.calls[0]
    assert "pg_advisory_xact_lock" in statement
    assert "hashtextextended" in statement
    assert params == {"lock_key": "purchase-import-batch:batch-123"}


def test_non_process_purchase_import_request_does_not_lock():
    conn = RecordingConnection("postgresql")

    locked = acquire_purchase_import_processing_lock(
        conn,
        "POST",
        "/api/purchase-import-batches/batch-123/pull",
    )

    assert locked is False
    assert conn.calls == []


def test_read_process_request_does_not_lock():
    conn = RecordingConnection("postgresql")

    locked = acquire_purchase_import_processing_lock(
        conn,
        "GET",
        "/api/purchase-import-batches/batch-123/process",
    )

    assert locked is False
    assert conn.calls == []


def test_non_postgresql_runtime_does_not_use_postgresql_lock_function():
    conn = RecordingConnection("sqlite")

    locked = acquire_purchase_import_processing_lock(
        conn,
        "POST",
        "/api/purchase-import-batches/batch-123/process",
    )

    assert locked is False
    assert conn.calls == []


def test_process_route_acquires_lock_inside_its_mutation_transaction():
    main_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
    source = main_path.read_text(encoding="utf-8")
    route_start = source.index("def process_purchase_import_batch")
    route_source = source[route_start:]

    transaction_offset = route_source.index("with engine.begin() as conn:")
    lock_offset = route_source.index("acquire_purchase_import_processing_lock(")
    batch_read_offset = route_source.index("batch = conn.execute(")

    assert transaction_offset < lock_offset < batch_read_offset


def test_http_guard_does_not_hold_processing_lock_on_a_separate_connection():
    import inspect

    source = inspect.getsource(install_unpacking_household_object_guard)
    assert "acquire_purchase_import_processing_lock(" not in source
