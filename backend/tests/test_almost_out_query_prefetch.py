"""Read-only Bijna op projection prefetch: identity, ordering and query counts."""
from __future__ import annotations

from app.services.almost_out_query_prefetch import prefetch_individual_almost_out


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class Connection:
    def __init__(self, inventory, events, purchases=()):
        self.inventory = inventory
        self.events = events
        self.purchases = purchases
        self.queries = []

    def execute(self, stmt, params):
        sql = str(stmt)
        self.queries.append((sql, params))
        assert "household_id = :household_id" in sql
        assert params["household_id"] == "household-A"
        if "FROM inventory i" in sql:
            assert "COALESCE(i.aantal, 0) > 0" in sql
            assert "lower(trim(i.naam)) IN" in sql
            return Rows(self.inventory)
        if "FROM inventory_events" in sql:
            assert "article_id IN" in sql and "lower(trim(article_name)) IN" in sql
            if "event_type IN ('purchase', 'auto_repurchase')" in sql:
                return Rows(self.purchases)
            return Rows(self.events)
        raise AssertionError("Unexpected query")


def article(identifier, name, product=None):
    return {"id": identifier, "naam": name, "global_product_id": product,
            "custom_name": None}


def stock(identifier, name, quantity):
    return {
        "id": identifier, "article_name": name, "quantity": quantity,
        "space_id": None, "sublocation_id": None,
        "space_name": "", "sublocation_name": "", "status": "active",
    }


def event(identifier, article_id, name, quantity, *, event_type="purchase"):
    return {
        "id": identifier, "article_id": article_id, "article_name": name,
        "quantity": quantity, "event_type": event_type,
        "created_at": "2026-01-01T00:00:00Z",
        "purchase_date": "2026-01-01", "location_label": "",
    }


def test_replays_exact_name_and_id_membership_without_duplicate_events():
    articles = [
        article("a", "Melk", "catalog-1"),
        article("b", "HV Melk", "catalog-1"),
        article("c", "Groente"),
    ]
    connection = Connection(
        # Sorted as in the legacy SQL query; first row must stay primary.
        [stock("i-2", "HV Melk", 2), stock("i-1", "Melk", 1),
         stock("i-3", "Groente", 9)],
        [event("e-3", "c", "Groente", 9),
         event("e-2", "b", "HV Melk", 2),
         event("e-1", "a", "Melk", 1),
         # An event can match the name even if the source ID was legacy/unknown.
         event("e-0", "legacy", "Melk", 1)],
        [event("e-1", "a", "Melk", 1), event("e-2", "b", "HV Melk", 2)],
    )
    result = prefetch_individual_almost_out(
        connection, "household-A", articles, [articles[0], articles[2]],
        include_purchases=True)
    assert len(connection.queries) == 3, "One SQL read each for inventory/events/purchases"
    assert sorted(result) == ["a", "c"]
    milk = result["a"]
    assert [row["id"] for row in milk["inventory_rows"]] == ["i-2", "i-1"]
    assert [row["household_article_id"] for row in milk["inventory_rows"]] == ["a", "a"]
    assert [row["product_scope_article_ids"] for row in milk["inventory_rows"]] == [["a", "b"], ["a", "b"]]
    assert [row["id"] for row in milk["event_rows"]] == ["e-2", "e-1", "e-0"]
    assert [row["id"] for row in milk["purchase_rows"]] == ["e-1", "e-2"]
    assert [row["id"] for row in result["c"]["event_rows"]] == ["e-3"]
    assert [row["id"] for row in result["c"]["inventory_rows"]] == ["i-3"]
    assert result["a"]["inventory_rows"][0]["location_label"] == ""
    assert result["a"]["inventory_rows"][0]["quantity"] == 2.0
    assert result["a"]["event_rows"][0]["quantity"] == 2
    assert all("INSERT" not in sql and "UPDATE" not in sql and "DELETE" not in sql
               for sql, _args in connection.queries)


def test_no_prediction_horizon_omits_purchase_query():
    row = article("a", "Basmati")
    connection = Connection([stock("i-a", "Basmati", 1)], [event("e-a", "a", "Basmati", 1)])
    result = prefetch_individual_almost_out(
        connection, "household-A", [row], [row], include_purchases=False)
    assert len(connection.queries) == 2
    assert result["a"]["purchase_rows"] == []
    assert len(result["a"]["inventory_rows"]) == 1


def test_no_candidates_or_missing_article_does_not_access_database():
    row = article("valid", "Correct")
    connection = Connection([], [])
    assert prefetch_individual_almost_out(
        connection, "household-A", [row], [], include_purchases=True) == {}
    assert prefetch_individual_almost_out(
        connection, "household-A", [row],
        [article("unavailable", "Foreign")], include_purchases=True) == {}
    assert connection.queries == []


def test_same_name_is_not_grouping_authority():
    # Legacy name-based inventory lookup is preserved only inside a *single*
    # article evaluation. It never silently aggregates independent IDs.
    a = article("a", "Melk")
    b = article("b", "Melk")
    conn = Connection([stock("i", "Melk", 1)],
                      [event("e-a", "a", "Melk", 1)])
    result = prefetch_individual_almost_out(
        conn, "household-A", [a, b], [a, b], include_purchases=False)
    assert set(result) == {"a", "b"}
    assert result["a"]["inventory_rows"][0]["product_scope_article_ids"] == ["a"]
    assert result["b"]["inventory_rows"][0]["product_scope_article_ids"] == ["b"]
    assert [x["id"] for x in result["a"]["event_rows"]] == ["e-a"]
    assert [x["id"] for x in result["b"]["event_rows"]] == ["e-a"]
