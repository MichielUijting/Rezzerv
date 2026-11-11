"""Fail-closed regression contracts for retailer-queue drift migration.

These are isolated fakes; the normal PostgreSQL migration authority must
also run on a real disposable database before Ready.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261111_01_retailer_queue_schema_drift_repair.py"
spec = spec_from_file_location("retailer_queue_drift_revision", MODULE)
revision = module_from_spec(spec)
spec.loader.exec_module(revision)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, exists, healthy=True, dialect="postgresql"):
        self.exists = exists
        self.healthy = healthy
        self.dialect = SimpleNamespace(
            name=dialect,
            identifier_preparer=SimpleNamespace(quote_identifier=lambda value: '"' + value + '"'),
        )
        self.writes = []

    def execute(self, statement, params=None):
        if "current_schema()" in str(statement):
            return _Result("public")
        if "pg_trigger" in str(statement):
            return _Result("CREATE TRIGGER ... EXECUTE FUNCTION inhuis_maintenance_write_barrier()" if self.healthy else None)
        raise AssertionError("Unexpected SQL")

    def exec_driver_sql(self, sql):
        self.writes.append(("trigger", sql))

    def has_table(self, table, schema):
        assert table == "retailer_import_queue" and schema == "public"
        return self.exists

    def get_columns(self, table, schema):
        names = revision.COLUMNS if self.healthy else {"id", "household_id"}
        return [{"name": n} for n in names]

    def get_pk_constraint(self, table, schema):
        return {"constrained_columns": ["id"]}

    def get_check_constraints(self, table, schema):
        return [{"name": x} for x in (
            "ck_retailer_queue_provider", "ck_retailer_queue_status",
            "ck_retailer_queue_attempts",
        )]

    def get_unique_constraints(self, table, schema):
        return [{"name": "uq_retailer_import_queue_observation"}]

    def get_indexes(self, table, schema):
        return [{"name": "ix_retailer_import_queue_pending"}]


def _attach(monkeypatch, db):
    monkeypatch.setattr(revision.op, "get_bind", lambda: db)
    monkeypatch.setattr(revision, "inspect", lambda bind: db)
    def create_table(name, *columns):
        assert name == "retailer_import_queue"
        assert not db.exists
        db.exists = True
        db.writes.append(("table", name))
    monkeypatch.setattr(revision.op, "create_table", create_table)
    monkeypatch.setattr(revision.op, "create_index",
                        lambda *args: db.writes.append(("index", args[0])))


def test_missing_table_restored_with_original_index_and_maintenance_gate(monkeypatch):
    db = _FakeDB(exists=False)
    _attach(monkeypatch, db)
    revision.upgrade()
    assert [x[0] for x in db.writes] == ["table", "index", "trigger"]
    assert "inhuis_maintenance_write_barrier" in db.writes[-1][1]


def test_existing_complete_queue_never_recreated_or_modified(monkeypatch):
    db = _FakeDB(exists=True)
    _attach(monkeypatch, db)
    revision.upgrade()
    assert db.writes == []


def test_partial_existing_queue_fails_without_any_write(monkeypatch):
    db = _FakeDB(exists=True, healthy=False)
    _attach(monkeypatch, db)
    with pytest.raises(RuntimeError, match="incomplete column"):
        revision.upgrade()
    assert db.writes == []


def test_missing_maintenance_trigger_fails_closed(monkeypatch):
    db = _FakeDB(exists=True)
    _attach(monkeypatch, db)
    db.execute = lambda statement, params=None: (
        _Result("public") if "current_schema()" in str(statement) else _Result(None)
    )
    with pytest.raises(RuntimeError, match="maintenance write barrier"):
        revision.upgrade()
    assert db.writes == []


def test_sqlite_is_not_modified(monkeypatch):
    db = _FakeDB(exists=False, dialect="sqlite")
    _attach(monkeypatch, db)
    revision.upgrade()
    assert db.writes == []


def test_queue_downgrade_never_drops_history():
    with pytest.raises(RuntimeError, match="Refuse destructive"):
        revision.downgrade()
