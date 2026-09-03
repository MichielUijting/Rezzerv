from app.services.household_article_events_postgresql_contract import (
    load_household_article_events,
)


class _MappingsResult:
    def __init__(self, *, first=None, rows=None):
        self._first = first
        self._rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, dict(params)))
        if "FROM household_articles" in sql:
            return _MappingsResult(first={"id": "article-1", "naam": "SOEPGR BASIS"})
        if "FROM inventory_events" in sql:
            return _MappingsResult(rows=[{
                "id": "event-1",
                "article_id": "article-1",
                "household_article_id": "article-1",
                "article_name": "SOEPGR BASIS",
                "location_id": None,
                "location_label": "",
                "event_type": "purchase",
                "quantity": 1,
                "old_quantity": 0,
                "new_quantity": 1,
                "source": "receipt",
                "note": "PO",
                "created_at": "2026-09-03T20:00:00+00:00",
            }])
        raise AssertionError(sql)


def test_article_history_query_uses_canonical_household_article_name_column():
    conn = _FakeConnection()

    load_household_article_events(conn, "household-1", "article-1")

    article_sql, params = conn.calls[0]
    normalized = " ".join(article_sql.split())
    assert "SELECT id, naam FROM household_articles" in normalized
    assert "SELECT id, name FROM household_articles" not in normalized
    assert params == {
        "household_article_id": "article-1",
        "household_id": "household-1",
    }


def test_article_history_query_is_postgresql_native_and_locationless_safe():
    conn = _FakeConnection()

    payload = load_household_article_events(conn, "household-1", "article-1")

    assert payload["article_id"] == "article-1"
    assert payload["items"][0]["event_type"] == "purchase"
    assert payload["items"][0]["location_id"] is None

    event_sql, params = conn.calls[1]
    normalized = " ".join(event_sql.split())
    assert "datetime(" not in event_sql.lower()
    assert "ORDER BY created_at DESC NULLS LAST, id DESC" in normalized
    assert "household_article_id = :household_article_id" in normalized
    assert params == {
        "household_id": "household-1",
        "household_article_id": "article-1",
        "article_name": "SOEPGR BASIS",
    }
