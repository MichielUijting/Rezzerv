from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import uuid


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, params):
        self.calls.append((str(statement), dict(params)))
        return None


def _load_create_inventory_event():
    source = MAIN_PATH.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(MAIN_PATH))
    function_node = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_inventory_event"
    )
    isolated = ast.Module(body=[function_node], type_ignores=[])
    ast.fix_missing_locations(isolated)

    namespace = {
        "datetime": datetime,
        "timezone": timezone,
        "uuid": uuid,
        "text": lambda value: value,
        "require_resolved_location": lambda value: value,
        "resolve_or_create_inventory_household_article": (
            lambda conn, *, household_id, article_name, preferred_household_article_id, source:
            str(preferred_household_article_id)
        ),
        "normalize_purchase_date": lambda value: str(value or "").strip() or None,
    }
    exec(compile(isolated, str(MAIN_PATH), "exec"), namespace)
    return namespace["create_inventory_event"]


def _location() -> dict:
    return {
        "location_id": "sub-1",
        "location_label": "Keuken / Fruitschaal",
        "space_id": "space-1",
        "sublocation_id": "sub-1",
    }


def test_purchase_writer_populates_migration_owned_temporal_columns():
    create_inventory_event = _load_create_inventory_event()
    conn = _FakeConnection()

    create_inventory_event(
        conn,
        household_id="H1",
        article_id="A1",
        article_name="Bananen",
        resolved_location=_location(),
        event_type="purchase",
        quantity=2,
        source="store_import",
        note="receipt purchase",
        purchase_date="2026-08-04",
    )

    assert len(conn.calls) == 1
    statement, params = conn.calls[0]
    for column in (
        "effective_at",
        "recorded_at",
        "effective_at_precision",
        "event_priority",
        "source_reference",
        "source_line_id",
        "replayed_at",
    ):
        assert column in statement
    assert params["effective_at"] == "2026-08-04T00:00:00+00:00"
    assert params["effective_at_precision"] == "date"
    assert params["event_priority"] == 10
    assert str(params["recorded_at"]).strip()


def test_consume_writer_uses_recorded_time_and_consume_priority():
    create_inventory_event = _load_create_inventory_event()
    conn = _FakeConnection()

    create_inventory_event(
        conn,
        household_id="H1",
        article_id="A1",
        article_name="Bananen",
        resolved_location=_location(),
        event_type="consume",
        quantity=1,
        source="manual",
        note="consume",
    )

    assert len(conn.calls) == 1
    _statement, params = conn.calls[0]
    assert params["effective_at"] == params["recorded_at"]
    assert params["effective_at_precision"] == "datetime"
    assert params["event_priority"] == 40
