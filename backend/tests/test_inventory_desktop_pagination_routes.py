"""Desktop Voorraad first-page grouping, identity, data scope and GPC contracts.

No SQLite harness: PostgreSQL CI remains the integration authority.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.inventory_desktop_pagination_routes as desktop


def _row(number, group_name, article_id=None, location="Keuken", quantity=1):
    return {
        "id": f"stock-{number}",
        "artikel": group_name,
        "aantal": quantity,
        "household_article_id": article_id,
        "locatie": location,
        "sublocatie": "",
        "space_id": None,
        "sublocation_id": None,
    }


class _Result:
    def __init__(self, records=None, scalar_value=None):
        self.records = list(records or [])
        self.scalar_value = scalar_value

    def scalar(self):
        return self.scalar_value

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return self.records


class _PageConnection:
    def __init__(self, group_keys, stock_rows):
        self.keys = group_keys
        self.stock_rows = stock_rows
        self.calls = []

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, dict(params)))
        assert params["household_id"] == "household-1"
        assert "i.household_id = :household_id" in sql
        assert "COALESCE(i.status, 'active') = 'active'" in sql
        assert "COALESCE(i.aantal, 0) > 0" in sql
        if "SELECT COUNT(*)" in sql:
            assert "GROUP BY" in sql
            return _Result(scalar_value=len(self.keys))
        if "SELECT group_key FROM" in sql:
            assert "LIMIT :page_size OFFSET :offset" in sql
            assert "ORDER BY sort_name, sort_id" in sql
            offset = params["offset"]
            return _Result(self.keys[offset:offset + params["page_size"]])
        assert "group_keys" in params
        assert "IN (__[POSTCOMPILE_group_keys])" in sql
        allowed = set(params["group_keys"])
        assert len(allowed) <= 10
        return _Result([
            row for row in self.stock_rows
            if "name:" + row["artikel"].strip().lower() in allowed
        ])


def test_first_ten_desktop_name_groups_keep_all_physical_locations():
    names = ["Melk"] + [f"Z-Artikel {i:02d}" for i in range(23)]
    keys = ["name:" + name.lower() for name in names]
    stock = [_row("a", "Melk", "ha-milk", "Keuken", 2)]
    stock.append(_row("b", "Melk", "ha-milk", "Berging", 3))
    stock.extend(_row(i, name) for i, name in enumerate(names[1:]))
    conn = _PageConnection(keys, stock)

    first = desktop._select_desktop_page(conn, "household-1", page=1, page_size=10)
    assert first["total"] == 24
    assert first["page_size"] == 10
    assert len(first["rows"]) == 11
    assert {row["id"] for row in first["rows"] if row["artikel"] == "Melk"} == {
        "stock-a", "stock-b"
    }
    assert conn.calls[2][1]["group_keys"] == keys[:10]

    second = desktop._select_desktop_page(conn, "household-1", page=2, page_size=10)
    assert len(second["rows"]) == 10
    assert not any(row["artikel"] == "Melk" for row in second["rows"])
    assert conn.calls[5][1]["group_keys"] == keys[10:20]

    last = desktop._select_desktop_page(conn, "household-1", page=3, page_size=10)
    assert len(last["rows"]) == 4

    out_of_range = desktop._select_desktop_page(
        conn, "household-1", page=4, page_size=10
    )
    assert out_of_range["total"] == 24
    assert out_of_range["rows"] == []
    assert len(conn.calls) == 11  # no detail query for empty page


def test_empty_name_is_never_combined_with_another_unidentified_item():
    key = desktop._DESKTOP_GROUP_KEY
    assert "THEN 'name:' || lower(TRIM(i.naam))" in key
    assert "ELSE 'inventory:' || CAST(i.id AS TEXT)" in key
    assert desktop._DESKTOP_WHERE.count("i.household_id = :household_id") == 1


def test_http_page_uses_active_authorized_household_not_request_household(monkeypatch):
    from app import main as legacy

    stock = [_row("1", "Melk", "ha-1")]
    conn = _PageConnection(["name:melk"], stock)

    class _ConnectionContext:
        def __enter__(self):
            return conn

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(
        desktop, "engine", SimpleNamespace(connect=lambda: _ConnectionContext())
    )
    monkeypatch.setattr(
        legacy, "require_household_context", lambda token: (
            SimpleNamespace(token=token) if token == "Bearer okay" else None
        ),
    )
    monkeypatch.setattr(
        legacy, "household_context_from_runtime_context",
        lambda runtime: SimpleNamespace(active_household_id="household-1"),
    )

    page = desktop.desktop_inventory_page(
        page=1, page_size=10, authorization="Bearer okay"
    )
    assert page["total"] == 1
    assert page["rows"][0]["household_article_id"] == "ha-1"
    assert len(conn.calls) == 3


def test_classification_enrichment_is_limited_to_visible_authorized_articles(monkeypatch):
    from app import main as legacy

    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, *_):
            return False

    calls = []

    def fake_projection(_connection, household_id, ids):
        calls.append((household_id, list(ids)))
        return {"ha-1": {"gpc_brick_name": "Zuivel"}}

    monkeypatch.setattr(desktop, "engine", SimpleNamespace(begin=lambda: _Context()))
    monkeypatch.setattr(desktop, "dutch_gpc_by_household_article", fake_projection)
    monkeypatch.setattr(legacy, "require_household_context", lambda _token: object())
    monkeypatch.setattr(
        legacy, "household_context_from_runtime_context",
        lambda _ctx: SimpleNamespace(active_household_id="household-1"),
    )
    result = desktop.desktop_inventory_page_classifications(
        household_article_ids=["ha-1", "ha-1", ""], authorization="Bearer okay"
    )
    assert calls == [("household-1", ["ha-1"])]
    assert result == {"by_article": {"ha-1": {"gpc_brick_name": "Zuivel"}}}

    with pytest.raises(HTTPException) as raised:
        desktop.desktop_inventory_page_classifications(
            household_article_ids=[str(i) for i in range(201)],
            authorization="Bearer okay",
        )
    assert raised.value.status_code == 422


def test_first_screen_sql_does_not_do_full_household_gpc_assignment():
    assert "global_product_gpc_bricks" not in desktop._DESKTOP_VISIBLE_ROWS_SQL
    assert "LIMIT :page_size OFFSET :offset" in desktop._DESKTOP_PAGE_KEYS_SQL
    assert "AND " + desktop._DESKTOP_GROUP_KEY + " IN :group_keys" in (
        desktop._DESKTOP_VISIBLE_ROWS_SQL
    )
