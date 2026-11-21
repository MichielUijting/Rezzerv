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

    def scalars(self):
        return self

    def all(self):
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
        if "FROM household_receipt_history_cutovers" in query:
            assert "WHERE EXISTS" in query and "inventory_events" in query
            return Result([])
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
    assert outcome == {
        "status": "applied", "linked": 3, "limit_reached": False,
        "historical_auto_stock": {
            "processed": 0, "created": 0, "revised": 0,
            "skipped": 0, "failed": 0, "status": "checked",
        },
    }
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



def test_ingest_and_reparse_signal_only_after_transaction_scope():
    """Regressions must not make automatic matching part of a bon DB commit."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "services"
              / "receipt_service.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    for function_name in ("ingest_receipt", "reparse_receipt"):
        function = next(node for node in module.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == function_name)
        transaction_blocks = [node for node in function.body
                              if isinstance(node, ast.With)
                              and any(isinstance(context.context_expr, ast.Call)
                                      and isinstance(context.context_expr.func, ast.Attribute)
                                      and context.context_expr.func.attr == "begin"
                                      for context in node.items)]
        assert transaction_blocks, function_name
        trigger_blocks = [node for node in function.body
                          if isinstance(node, ast.If)
                          and any(isinstance(child, ast.Call)
                                  and isinstance(child.func, ast.Name)
                                  and child.func.id == "signal_receipt_committed"
                                  for child in ast.walk(node))]
        assert len(trigger_blocks) == 1, function_name
        assert trigger_blocks[0].lineno > max(node.end_lineno for node in transaction_blocks)
        assert any(isinstance(node, ast.Return) for node in function.body
                   if node.lineno > trigger_blocks[0].end_lineno)



def test_catalog_identity_confirmation_only_wakes_after_successful_write():
    """A failed HTTP confirmation never schedules a supposedly confirmed proof."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "api"
              / "catalog_routes.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    expected = {
        "materialize_existing_ed2_manual_barcodes": 1,
        "save_ed2_manual_barcode": 3,
    }
    for name, expected_signals in expected.items():
        function = next(n for n in module.body
                        if isinstance(n, ast.FunctionDef) and n.name == name)
        signals = [n for n in ast.walk(function)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "signal_receipt_committed"]
        assert len(signals) == expected_signals, name
        transactions = [n for n in ast.walk(function)
                        if isinstance(n, ast.With)
                        and any(isinstance(item.context_expr, ast.Call)
                                and isinstance(item.context_expr.func, ast.Attribute)
                                and item.context_expr.func.attr == "begin"
                                for item in n.items)]
        assert transactions, name
        for signal in signals:
            assert not any(t.lineno < signal.lineno < t.end_lineno for t in transactions), name
