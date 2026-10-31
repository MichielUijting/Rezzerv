"""Pure AH background sync authority checks: no PostgreSQL or retailer connection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest

from app.services import ah_receipt_background_sync as worker
from app.services import ah_receipt_sync_service as sync_service


def test_due_calculation_rejects_unknown_and_recent_states():
    now = datetime.now(timezone.utc)
    assert worker._due(None, now)
    assert worker._due(now - timedelta(hours=2), now)
    assert not worker._due(now - timedelta(minutes=2), now)
    assert not worker._due("unrecognized value", now)
    assert worker._lock_key("household-a") == worker._lock_key("household-a")
    assert worker._lock_key("household-a") != worker._lock_key("household-b")


class FakeResult:
    def __init__(self, rows=None, value=None):
        self.rows = rows or []
        self.value = value

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalar(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def first(self):
        return {'enabled': self.value}


class FakeConnection:
    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, stmt, values=None):
        sql = str(stmt)
        if "SELECT state FROM maintenance_control" in sql:
            return FakeResult(value=self.engine.maintenance_state)
        if "FROM platform_feature_flags" in sql:
            return FakeResult(value=self.engine.imports_enabled)
        if "SELECT household_id, last_sync_at" in sql:
            return FakeResult(rows=self.engine.rows)
        if "pg_try_advisory_lock" in sql:
            return FakeResult(value=self.engine.lock_enabled)
        if "pg_advisory_unlock" in sql:
            return FakeResult(value=True)
        if "SELECT last_sync_at" in sql:
            return FakeResult(value=self.engine.refreshed_at)
        raise AssertionError("Unexpected SQL")


class FakeEngine:
    def __init__(self, rows, lock_enabled=True, refreshed_at=None, dialect="postgresql", maintenance_state="normal", imports_enabled=True):
        self.dialect = SimpleNamespace(name=dialect)
        self.rows = rows
        self.lock_enabled = lock_enabled
        self.refreshed_at = refreshed_at
        self.maintenance_state = maintenance_state
        self.imports_enabled = imports_enabled

    def connect(self):
        return FakeConnection(self)


def test_platform_import_pause_skips_new_ah_sync_and_resumes(monkeypatch, tmp_path):
    engine = FakeEngine([{"household_id": "household-a", "last_sync_at": None}], imports_enabled=False)
    calls = []
    monkeypatch.setattr(worker, "_admitted_ah_sync", lambda *_args: calls.append("import"))
    assert worker.sync_due_ah_households(engine, tmp_path)["due"] == 0
    assert calls == []
    engine.imports_enabled = True
    assert worker.sync_due_ah_households(engine, tmp_path)["completed"] == 1
    assert calls == ["import"]


def test_background_worker_processes_only_due_households(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    engine = FakeEngine([
        {"household_id": "household-a", "last_sync_at": now - timedelta(hours=2)},
        {"household_id": "household-b", "last_sync_at": now - timedelta(minutes=2)},
    ])
    processed = []
    monkeypatch.setattr(worker, "_admitted_ah_sync", lambda _e, _root, household_id: processed.append(household_id))
    result = worker.sync_due_ah_households(engine, tmp_path)
    assert processed == ["household-a"]
    assert result == {"due": 1, "completed": 1, "failed": 0, "locked": 0}


def test_background_worker_skips_locked_and_refreshed_households(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rows = [{"household_id": "household-a", "last_sync_at": now - timedelta(hours=2)}]
    processed = []
    monkeypatch.setattr(worker, "_admitted_ah_sync", lambda _e, _root, household_id: processed.append(household_id))
    locked = worker.sync_due_ah_households(FakeEngine(rows, lock_enabled=False), tmp_path)
    refreshed = worker.sync_due_ah_households(FakeEngine(rows, refreshed_at=now), tmp_path)
    assert locked["locked"] == 1
    assert refreshed["completed"] == 0
    assert processed == []


def test_background_worker_never_runs_without_postgresql(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "_admitted_ah_sync", lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected write")))
    result = worker.sync_due_ah_households(FakeEngine([], dialect="sqlite"), tmp_path)
    assert result["completed"] == 0


def test_registered_writer_requires_maintenance_admission():
    # The inner function is covered by the existing writer_operation contract.
    assert hasattr(worker._admitted_ah_sync, "__wrapped__")
    assert worker.AH_AUTO_SYNC_LIMIT == 100


def test_background_scheduler_pauses_during_maintenance(monkeypatch, tmp_path):
    engine = FakeEngine([{"household_id": "household-a", "last_sync_at": None}], maintenance_state="draining")
    monkeypatch.setattr(worker, "_admitted_ah_sync", lambda *_args: (_ for _ in ()).throw(AssertionError("no import expected")))
    assert worker.sync_due_ah_households(engine, tmp_path) == {
        "due": 0, "completed": 0, "failed": 0, "locked": 0,
    }
    engine.maintenance_state = "normal"
    monkeypatch.setattr(worker, "_admitted_ah_sync", lambda *_args: None)
    assert worker.sync_due_ah_households(engine, tmp_path)["completed"] == 1


def test_drain_between_households_does_not_start_next_import(monkeypatch, tmp_path):
    engine = FakeEngine([
        {"household_id": "household-a", "last_sync_at": None},
        {"household_id": "household-b", "last_sync_at": None},
    ])
    completed = []

    def first_only(_engine, _root, household_id):
        completed.append(household_id)
        engine.maintenance_state = "draining"

    monkeypatch.setattr(worker, "_admitted_ah_sync", first_only)
    assert worker.sync_due_ah_households(engine, tmp_path)["completed"] == 1
    assert completed == ["household-a"]


def test_app_shutdown_finishes_current_household_but_skips_next(monkeypatch, tmp_path):
    engine = FakeEngine([
        {"household_id": "household-a", "last_sync_at": None},
        {"household_id": "household-b", "last_sync_at": None},
    ])
    stopped = False
    completed = []

    def finish_first(_engine, _root, household_id):
        nonlocal stopped
        completed.append(household_id)
        stopped = True

    monkeypatch.setattr(worker, "_admitted_ah_sync", finish_first)
    result = worker.sync_due_ah_households(engine, tmp_path, lambda: stopped)
    assert result["completed"] == 1
    assert completed == ["household-a"]


def test_known_preimport_failure_is_completed_without_claiming_sync_success(monkeypatch, tmp_path):
    def unavailable(*_args, **_kwargs):
        raise sync_service.AHPreImportFailure("No import started")

    monkeypatch.setattr(sync_service, "sync_ah_receipts", unavailable)
    assert worker._admitted_ah_sync.__wrapped__(None, tmp_path, "household-a") is False


def test_unclassified_import_failure_must_remain_unresolved(monkeypatch, tmp_path):
    def interrupted(*_args, **_kwargs):
        raise RuntimeError("unknown state after import started")

    monkeypatch.setattr(sync_service, "sync_ah_receipts", interrupted)
    with pytest.raises(RuntimeError, match="unknown state"):
        worker._admitted_ah_sync.__wrapped__(None, tmp_path, "household-a")


def test_preimport_failure_counts_as_failed_scheduler_attempt(monkeypatch, tmp_path):
    engine = FakeEngine([{"household_id": "household-a", "last_sync_at": None}])
    monkeypatch.setattr(worker, "_admitted_ah_sync", lambda *_args: False)
    assert worker.sync_due_ah_households(engine, tmp_path) == {
        "due": 1, "completed": 0, "failed": 1, "locked": 0
    }


def test_receipt_list_error_is_explicitly_preimport(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_service, "get_ah_session", lambda *_args: object())
    monkeypatch.setattr(sync_service, "save_ah_session", lambda *_args: pytest.fail("unexpected mutation"))

    class UnavailableClient:
        def list_receipts(self, *_args, **_kwargs):
            raise OSError("retailer unavailable")

    with pytest.raises(sync_service.AHPreImportFailure):
        sync_service.sync_ah_receipts(
            None, tmp_path, household_id="household-a", client=UnavailableClient(),
            classify_preimport_failures=True,
        )
    with pytest.raises(OSError, match="retailer unavailable"):
        sync_service.sync_ah_receipts(None, tmp_path, household_id="household-a", client=UnavailableClient())


def test_missing_or_unreadable_ah_session_is_preimport(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_service, "get_ah_session", lambda *_args: None)
    with pytest.raises(ValueError, match="niet gekoppeld"):
        sync_service.sync_ah_receipts(None, tmp_path, household_id="household-a", client=object())
    with pytest.raises(sync_service.AHPreImportFailure):
        sync_service.sync_ah_receipts(
            None, tmp_path, household_id="household-a", client=object(),
            classify_preimport_failures=True,
        )

    def unreadable(*_args):
        raise ValueError("invalid session material")

    monkeypatch.setattr(sync_service, "get_ah_session", unreadable)
    with pytest.raises(sync_service.AHPreImportFailure):
        sync_service.sync_ah_receipts(
            None, tmp_path, household_id="household-a", client=object(),
            classify_preimport_failures=True,
        )
