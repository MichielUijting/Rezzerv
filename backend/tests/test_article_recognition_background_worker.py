"""Private article recognition: security, maintenance, evidence and job bounds.

No test connects to an existing household database.
"""
from types import SimpleNamespace

import pytest

from app.services.article_recognition_service_actor import (
    SERVICE_ACTOR_ID, validate_recognition_actor,
)
from app.services import article_recognition_background_worker as worker


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class Conn:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, state="normal", locked=True):
        self.state, self.locked = state, locked
        self.statements = []

    def execute(self, sql, params=None):
        query = str(sql)
        self.statements.append((query, params))
        if "maintenance_control" in query:
            return Result(self.state)
        if "pg_try_advisory_xact_lock" in query:
            return Result(self.locked)
        raise AssertionError("Unexpected database query")


def test_system_actor_cannot_be_injected_as_a_superuser():
    validate_recognition_actor("real-user-id", "platform_user")
    validate_recognition_actor(SERVICE_ACTOR_ID, "system_service")
    with pytest.raises(ValueError):
        validate_recognition_actor("member", "system_service")
    with pytest.raises(ValueError):
        validate_recognition_actor(SERVICE_ACTOR_ID, "platform_user")
    with pytest.raises(ValueError):
        validate_recognition_actor("", "system_service")
    with pytest.raises(ValueError):
        validate_recognition_actor(None, "platform_user")
    with pytest.raises(ValueError):
        validate_recognition_actor("real-user-id", "unknown")


@pytest.mark.parametrize("state", ["locked", "draining", "blocked", None])
def test_maintenance_gate_denies_background_writes(monkeypatch, state):
    from app.services import automatic_curated_identity_matching_service as curated
    from app.services import proven_exact_receipt_name_service as exact
    monkeypatch.setattr(curated, "automatically_match_curated_receipts",
                        lambda *a, **kw: pytest.fail("No writes during maintenance"))
    monkeypatch.setattr(exact, "automatically_match_proven_exact_names",
                        lambda *a, **kw: pytest.fail("No writes during maintenance"))
    conn = Conn(state=state)
    assert worker.perform_recognition_pass(conn)["status"] == "paused"
    assert len(conn.statements) == 1


def test_busy_global_lock_does_not_start_parallel_matching(monkeypatch):
    from app.services import automatic_curated_identity_matching_service as curated
    monkeypatch.setattr(curated, "automatically_match_curated_receipts",
                        lambda *a, **kw: pytest.fail("Global lock not acquired"))
    assert worker.perform_recognition_pass(Conn(locked=False))["status"] == "busy"


def test_matching_uses_only_private_service_actor_and_existing_authorities(monkeypatch):
    from app.services import automatic_curated_identity_matching_service as curated
    from app.services import proven_exact_receipt_name_service as exact
    calls = []

    def family(conn, *, actor_id, actor_type):
        calls.append(("curated", actor_id, actor_type))
        return {"ok": True, "linked": 1, "barcode_written": False,
                "synonyms_created": 0, "limit_reached": False}

    def names(conn, *, actor_id, actor_type):
        calls.append(("exact", actor_id, actor_type))
        return {"ok": True, "linked": 2, "barcode_written": False,
                "limit_reached": False}

    monkeypatch.setattr(curated, "automatically_match_curated_receipts", family)
    monkeypatch.setattr(exact, "automatically_match_proven_exact_names", names)
    outcome = worker.perform_recognition_pass(Conn())
    assert outcome == {"status": "applied", "linked": 3, "limit_reached": False}
    assert calls == [
        ("curated", SERVICE_ACTOR_ID, "system_service"),
        ("exact", SERVICE_ACTOR_ID, "system_service"),
    ]


@pytest.mark.parametrize("response", [
    {"ok": False, "linked": 0, "barcode_written": False},
    {"ok": True, "linked": 0, "barcode_written": True},
    {"ok": True, "linked": 1, "barcode_written": False, "synonyms_created": 1},
])
def test_internal_match_result_must_not_claim_unsafe_success(monkeypatch, response):
    from app.services import automatic_curated_identity_matching_service as curated
    from app.services import proven_exact_receipt_name_service as exact
    monkeypatch.setattr(curated, "automatically_match_curated_receipts",
                        lambda *a, **kw: response)
    monkeypatch.setattr(exact, "automatically_match_proven_exact_names",
                        lambda *a, **kw: {"ok": True, "linked": 0, "barcode_written": False})
    with pytest.raises(RuntimeError, match="veilig"):
        worker.perform_recognition_pass(Conn())


def test_sqlite_cannot_execute_private_postgresql_matching():
    conn = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    assert worker.perform_recognition_pass(conn)["status"] == "unavailable"


def test_postcommit_wake_uses_no_user_or_product_arguments():
    worker._RECEIPT_COMMITTED.clear()
    worker.signal_receipt_committed()
    assert worker._RECEIPT_COMMITTED.is_set()
    worker.signal_receipt_committed()
    assert worker._RECEIPT_COMMITTED.is_set()
    worker._RECEIPT_COMMITTED.clear()
