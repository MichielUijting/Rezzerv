from contextlib import contextmanager
from types import SimpleNamespace
import inspect

from app.services.inventory_location_household_patch import (
    _clear_selected_locationless_targets,
    install_inventory_location_household_patch,
)


class _FakeResult:
    rowcount = 1


class _FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), dict(params)))
        return _FakeResult()


class _FakeEngine:
    def __init__(self):
        self.connection = _FakeConnection()

    @contextmanager
    def begin(self):
        yield self.connection


def test_locationless_compat_clears_only_selected_stale_targets():
    engine = _FakeEngine()
    main_module = SimpleNamespace(engine=engine)

    updated = _clear_selected_locationless_targets(main_module, "batch-1")

    assert updated == 1
    assert len(engine.connection.calls) == 1
    statement, params = engine.connection.calls[0]
    normalized = " ".join(statement.split())
    assert "SET target_location_id = NULL" in normalized
    assert "location_override_mode = 'cleared'" in normalized
    assert "COALESCE(review_decision, 'pending') = 'selected'" in normalized
    assert "target_location_id IS NOT NULL" in normalized
    assert params == {"batch_id": "batch-1"}


def test_locationless_process_contract_covers_ui_selected_only_and_ready_only():
    source = inspect.getsource(install_inventory_location_household_patch)

    assert '{"ready_only", "selected_only"}' in source
    assert "configuration.location_tracking_level != LOCATION_NONE" in source
    assert "_clear_selected_locationless_targets(main_module, batch_id)" in source
    assert "_process_locationless_ready_only_batch(" in source
    assert "route.endpoint = process_purchase_import_batch_with_locationless_legacy_compat" in source


def test_locationless_selected_only_preserves_regular_selected_only_semantics():
    source = inspect.getsource(install_inventory_location_household_patch)

    assert 'if mode == "selected_only":' in source
    selected_branch = source.split('if mode == "selected_only":', 1)[1]
    selected_branch = selected_branch.split("return _process_locationless_ready_only_batch(", 1)[0]
    assert "return location_policy_endpoint(batch_id, payload, authorization)" in selected_branch


def test_locationless_compat_keeps_policy_context_active_during_inventory_writes():
    source = inspect.getsource(install_inventory_location_household_patch)

    assert "token = _processing_household_id.set(household_id)" in source
    assert "_processing_household_id.reset(token)" in source