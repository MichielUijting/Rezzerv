"""Fail-closed lifecycle proof without a live database or retailer account."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import retailer_import_queue_worker as worker


@pytest.fixture(autouse=True)
def platform_import_enabled(monkeypatch):
    monkeypatch.setattr(worker, "is_platform_feature_enabled", lambda *_args: True)


class _Result:
    def __init__(self, value=None):
        self.value = value
        self.rowcount = 1

    def scalar_one_or_none(self):
        return self.value


class _Connection:
    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement, values=None):
        query = str(statement)
        if "SELECT state FROM maintenance_control" in query:
            return _Result(self.engine.state)
        if "UPDATE retailer_import_queue" in query:
            self.engine.updated.append((query, values))
            return _Result()
        raise AssertionError("Unexpected SQL in unit test")


class _Engine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, state="normal"):
        self.state = state
        self.updated = []

    def connect(self):
        return _Connection(self)

    def begin(self):
        return _Connection(self)


def _claim():
    return {
        "id": "queue-1", "household_id": "house-1", "provider": "lidl",
        "external_receipt_id": "12345678", "operation_id": "operation-1",
    }


def test_pause_during_maintenance_never_claims_or_imports(monkeypatch, tmp_path):
    engine = _Engine("draining")
    monkeypatch.setattr(worker, "_claim_one", lambda *_: (_ for _ in ()).throw(AssertionError("claim")))
    assert worker.process_one_staged_receipt(engine, tmp_path) is False
    engine.state = "locked"
    assert worker.process_one_staged_receipt(engine, tmp_path) is False


def test_manual_platform_pause_leaves_pending_receipts_untouched(monkeypatch, tmp_path):
    engine = _Engine()
    monkeypatch.setattr(worker, "is_platform_feature_enabled", lambda *_args: False)
    monkeypatch.setattr(worker, "_claim_one", lambda *_: (_ for _ in ()).throw(AssertionError("claim during pause")))
    assert worker.process_one_staged_receipt(engine, tmp_path) is False
    assert engine.updated == []


def test_success_records_result_and_closes_same_transaction(monkeypatch, tmp_path):
    engine = _Engine()
    monkeypatch.setattr(worker, "_claim_one", lambda *_: _claim())
    monkeypatch.setattr(worker, "_decode_claim", lambda *_: SimpleNamespace(provider="lidl"))
    monkeypatch.setattr(worker, "import_retailer_receipt", lambda *_args, **_kwargs: {
        "raw_receipt_id": "raw-one", "duplicate": False,
    })
    closed = []
    monkeypatch.setattr(worker, "complete_operation", lambda conn, *, operation_id: closed.append((conn, operation_id)))
    assert worker.process_one_staged_receipt(engine, tmp_path) is True
    assert engine.updated[0][1]["receipt_id"] == "raw-one"
    assert closed[0][1] == "operation-1"
    assert worker._operation.get() is None


def test_unknown_post_ingest_failure_preserves_admission(monkeypatch, tmp_path):
    engine = _Engine()
    monkeypatch.setattr(worker, "_claim_one", lambda *_: _claim())
    monkeypatch.setattr(worker, "_decode_claim", lambda *_: SimpleNamespace(provider="lidl"))
    monkeypatch.setattr(worker, "import_retailer_receipt", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("ambiguous")))
    monkeypatch.setattr(worker, "complete_operation", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("closed")))
    with pytest.raises(RuntimeError, match="ambiguous"):
        worker.process_one_staged_receipt(engine, tmp_path)
    assert engine.updated == []
    assert worker._operation.get() is None


def test_bad_ciphertext_can_be_reviewed_without_domain_ingest(monkeypatch, tmp_path):
    engine = _Engine()
    monkeypatch.setattr(worker, "_claim_one", lambda *_: _claim())
    monkeypatch.setattr(worker, "_decode_claim", lambda *_: (_ for _ in ()).throw(ValueError("decrypt_failed")))
    monkeypatch.setattr(worker, "import_retailer_receipt", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("ingest")))
    closed = []
    monkeypatch.setattr(worker, "complete_operation", lambda _conn, *, operation_id: closed.append(operation_id))
    assert worker.process_one_staged_receipt(engine, tmp_path) is True
    assert engine.updated[0][1]["reason"] == "decrypt_failed"
    assert closed == ["operation-1"]
