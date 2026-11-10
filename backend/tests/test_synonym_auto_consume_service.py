"""Targeted no-SQLite contracts for direct synonym repurchase processing."""
from __future__ import annotations

from app.services import synonym_auto_consume_service as svc

A = "a"
B = "b"


class _Result:
    def __init__(self, rows=(), scalar=None):
        self.rows = list(rows)
        self.value = scalar

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def scalar(self):
        return self.value


class _Conn:
    def __init__(self, *, pre_a=2, pre_b=3, purchases_a=0, purchases_b=0,
                 deducted_a=0, deducted_b=0, future=None, direct=False):
        self.stock = {"a": pre_a, "b": pre_b}
        self.purchases = {"a": purchases_a, "b": purchases_b}
        self.deducted = {"a": deducted_a, "b": deducted_b}
        self.future = future
        self.direct = direct
        self.queries = []

    def execute(self, stmt, params):
        sql = str(stmt)
        self.queries.append((sql, dict(params)))
        if "default_inventory_handling" in sql:
            article_id = params["article_id"]
            return _Result([{
                "id": article_id,
                "naam": "Melk " + article_id,
                "default_inventory_handling": "DIRECT_CONSUMPTION" if self.direct else "STOCK",
            }])
        if "MAX(substr(CAST(purchase_date" in sql:
            return _Result(scalar=self.future)
        if "SUM(aantal)" in sql:
            return _Result(scalar=self.stock[params["article_id"]])
        if "SELECT event_type, source, quantity" in sql:
            member = params["article_id"]
            rows = []
            if self.purchases[member]:
                rows.append({"event_type": "purchase", "source": "store_import",
                             "quantity": self.purchases[member]})
            if self.deducted[member]:
                rows.append({"event_type": "auto_repurchase", "source": "auto_repurchase",
                             "quantity": -self.deducted[member]})
            return _Result(rows)
        raise AssertionError(f"unexpected SQL: {sql}")


def _plan(monkeypatch, conn, *, mode="consume_purchased_quantity",
          new="a", bought=2, day="2026-11-10", household="h1",
          mode_for_article=None):
    monkeypatch.setattr(svc, "confirmed_household_synonym_pair",
                        lambda connection, household_id, article_id: ("a", "b"))
    return svc.plan_confirmed_synonym_deduction(
        conn,
        household_id=household,
        purchased_article_id=new,
        purchase_date=day,
        purchased_quantity=bought,
        household_mode=mode,
        effective_mode_for_article=mode_for_article or (lambda a, name: mode),
    )


def test_first_purchase_by_quantity_debits_partner_before_new_purchase(monkeypatch):
    conn = _Conn(pre_a=2, pre_b=3)
    plan = _plan(monkeypatch, conn)
    assert plan["requested_deduction_quantity"] == 2
    assert plan["allocations"] == [{"article_id": "b", "article_name": "Melk b",
                                    "quantity": 2}]
    assert plan["day_start_stock"] == 5
    assert all("household_id" in params for sql, params in conn.queries)


def test_all_existing_mode_removes_only_old_group_stock(monkeypatch):
    plan = _plan(monkeypatch, _Conn(), mode="consume_all_existing_before_purchase")
    assert plan["requested_deduction_quantity"] == 5
    assert [(r["article_id"], r["quantity"]) for r in plan["allocations"]] == [
        ("b", 3), ("a", 2)
    ]


def test_second_same_day_purchase_of_other_synonym_is_incremental(monkeypatch):
    # First purchase A2 consumed B2. A now holds old A2 + new A2, B old1.
    conn = _Conn(pre_a=4, pre_b=1, purchases_a=2, deducted_b=2)
    plan = _plan(monkeypatch, conn, new="b", bought=3)
    assert plan["day_start_stock"] == 5
    assert plan["cumulative_day_purchased_quantity"] == 5
    assert plan["requested_deduction_quantity"] == 3
    assert [(r["article_id"], r["quantity"]) for r in plan["allocations"]] == [
        ("a", 2), ("b", 1)
    ]


def test_all_existing_second_same_day_purchase_does_not_consume_again(monkeypatch):
    conn = _Conn(pre_a=2, pre_b=0, purchases_a=2, deducted_a=2, deducted_b=3)
    plan = _plan(monkeypatch, conn, mode="consume_all_existing_before_purchase",
                 new="b", bought=2)
    assert plan["requested_deduction_quantity"] == 0
    assert plan["allocations"] == []


def test_disabled_mode_never_looks_up_pair(monkeypatch):
    conn = _Conn()
    assert _plan(monkeypatch, conn, mode="none") is None
    assert conn.queries == []


def test_conflicting_article_override_keeps_existing_per_article_behavior(monkeypatch):
    assert _plan(monkeypatch, _Conn(), mode_for_article=lambda a, n:
                 "none" if a == "b" else "consume_purchased_quantity") is None


def test_direct_consumption_partner_cannot_be_consumed(monkeypatch):
    assert _plan(monkeypatch, _Conn(direct=True)) is None


def test_backdated_receipt_falls_back_to_legacy_single_product(monkeypatch):
    assert _plan(monkeypatch, _Conn(future="2026-11-11")) is None


def test_invalid_date_does_not_use_group(monkeypatch):
    assert _plan(monkeypatch, _Conn(), day="10-11-2026") is None


def test_group_allocation_posts_exact_member_events_and_protects_new_purchase():
    conn = _Conn()
    events = []
    consumed = []

    def event(connection, household_id, article_id, name, location, **kwargs):
        events.append((household_id, article_id, kwargs["quantity"]))
        return "event-" + article_id

    def stock(connection, household_id, name, qty, location, **kwargs):
        consumed.append((kwargs["household_article_id"], qty,
                         kwargs["protected_quantity_on_purchase_row"],
                         kwargs["protected_purchase_inventory_id"]))
        return {"applied_quantity": qty}

    result = svc.apply_confirmed_synonym_deduction(
        conn, household_id="h1", purchased_article_id="a",
        purchased_quantity=2, purchase_inventory_id="purchase-1",
        resolved_location={"location_id": None},
        plan={"purchase_day": "2026-11-10", "requested_deduction_quantity": 5,
              "allocations": [
                  {"article_id": "b", "article_name": "Melk b", "quantity": 3},
                  {"article_id": "a", "article_name": "Melk a", "quantity": 2},
              ]},
        create_auto_event=event, apply_stock_consumption=stock,
    )
    assert result == {"applied_quantity": 5, "event_ids": ["event-b", "event-a"]}
    assert events == [("h1", "b", 3), ("h1", "a", 2)]
    assert consumed == [("b", 3, 0, None), ("a", 2, 2, "purchase-1")]


def test_partial_mutation_fails_transaction_instead_of_claiming_success():
    conn = _Conn()

    def event(*args, **kwargs):
        return "event-1"

    def partial(*args, **kwargs):
        return {"applied_quantity": 0}

    try:
        svc.apply_confirmed_synonym_deduction(
            conn, household_id="h1", purchased_article_id="a",
            purchased_quantity=2, purchase_inventory_id="purchase-1",
            resolved_location={},
            plan={"purchase_day": "2026-11-10", "requested_deduction_quantity": 2,
                  "allocations": [{"article_id": "b", "article_name": "Melk b",
                                   "quantity": 2}]},
            create_auto_event=event, apply_stock_consumption=partial,
        )
    except RuntimeError as error:
        assert "voorraad en mutatiebewijs" in str(error)
    else:
        raise AssertionError("partial deduction must abort the transaction")
