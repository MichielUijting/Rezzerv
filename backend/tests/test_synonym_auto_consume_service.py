"""Targeted no-SQLite contracts for confirmed synonym-group repurchase processing."""
from __future__ import annotations

from app.services import synonym_auto_consume_service as svc

A = "a"
B = "b"


class _Result:
    def __init__(self, rows=(), scalar=None, rowcount=0):
        self.rows = list(rows)
        self.value = scalar
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def scalar(self):
        return self.value


class _Conn:
    def __init__(self, *, pre_a=2, pre_b=3, pre_c=0, purchases_a=0, purchases_b=0,
                 purchases_c=0, deducted_a=0, deducted_b=0, deducted_c=0,
                 future=None, direct=False, sizes=None):
        self.rows = {
            "a": [] if pre_a == 0 else [dict(id="inv-a", aantal=pre_a, space_id="loc-a", sublocation_id=None)],
            "b": [] if pre_b == 0 else [dict(id="inv-b", aantal=pre_b, space_id="loc-b", sublocation_id=None)],
            "c": [] if pre_c == 0 else [dict(id="inv-c", aantal=pre_c, space_id="loc-c", sublocation_id=None)],
        }
        self.purchases = {"a": purchases_a, "b": purchases_b, "c": purchases_c}
        self.deducted = {"a": deducted_a, "b": deducted_b, "c": deducted_c}
        self.future = future
        self.direct = direct
        self.queries = []
        self.fail_write = False
        self.sizes = sizes or {'a': (1, 'stuk'), 'b': (1, 'stuk'), 'c': (1, 'stuk')}

    def execute(self, stmt, params):
        sql = str(stmt)
        self.queries.append((sql, dict(params)))
        if "SELECT ha.id AS article_id" in sql:
            return _Result([
                {'article_id': article_id, 'size_value': self.sizes[article_id][0],
                 'size_unit': self.sizes[article_id][1], 'product_status': 'active'}
                for article_id in params['article_ids']
            ])
        if "default_inventory_handling" in sql:
            article_id = params["article_id"]
            return _Result([{
                "id": article_id,
                "naam": "Melk " + article_id,
                "default_inventory_handling": "DIRECT_CONSUMPTION" if self.direct else "STOCK",
            }])
        if "MAX(substr(CAST(purchase_date" in sql:
            return _Result(scalar=self.future)
        if "SELECT id, aantal, space_id, sublocation_id" in sql:
            article_id = params["article_id"]
            positions = self.rows[article_id]
            if "id=:inventory_id" in sql:
                positions = [p for p in positions if p["id"] == params["inventory_id"]]
            return _Result([dict(p) for p in positions])
        if "SELECT event_type, source, quantity" in sql:
            member = params["article_id"]
            rows = []
            if self.purchases[member]:
                location = self.rows[member][0]['sublocation_id'] or self.rows[member][0]['space_id']
                rows.append({"event_type": "purchase", "source": "store_import",
                             "quantity": self.purchases[member], "location_id": location})
            if self.deducted[member]:
                rows.append({"event_type": "auto_repurchase", "source": "auto_repurchase",
                             "quantity": -self.deducted[member], "location_id": None})
            return _Result(rows)
        if "UPDATE inventory SET" in sql or "DELETE FROM inventory" in sql:
            if self.fail_write:
                return _Result(rowcount=0)
            matches = [p for p in self.rows[params["article_id"]]
                       if p["id"] == params["inventory_id"] and p["aantal"] == params["before"]]
            if len(matches) != 1:
                return _Result(rowcount=0)
            if "UPDATE inventory SET" in sql:
                matches[0]["aantal"] = params["after"]
            else:
                self.rows[params["article_id"]].remove(matches[0])
            return _Result(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _plan(monkeypatch, conn, *, mode="consume_purchased_quantity",
          new="a", bought=2, day="2026-11-10", household="h1",
          mode_for_article=None):
    monkeypatch.setattr(svc, "confirmed_household_synonym_group",
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
    assert [(r["article_id"], r["inventory_id"], r["quantity"]) for r in plan["allocations"]] == [
        ("b", "inv-b", 2)
    ]
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


def test_group_allocation_posts_events_on_actual_inventory_locations():
    conn = _Conn()
    # This is the post-purchase state: A was 2 before buying 2 more.
    conn.rows["a"][0]["aantal"] = 4
    events = []

    def event(connection, household_id, article_id, name, location, **kwargs):
        events.append((household_id, article_id, kwargs["quantity"], location["location_id"]))
        return "event-" + article_id

    plan = {"purchase_day": "2026-11-10", "requested_deduction_quantity": 5,
            "allocations": [
                dict(article_id="b", article_name="Melk b", inventory_id="inv-b",
                     pre_quantity=3, space_id="loc-b", sublocation_id=None, quantity=3),
                dict(article_id="a", article_name="Melk a", inventory_id="inv-a",
                     pre_quantity=2, space_id="loc-a", sublocation_id=None, quantity=2),
            ]}
    result = svc.apply_confirmed_synonym_deduction(
        conn, household_id="h1", purchased_article_id="a",
        purchased_quantity=2, purchase_inventory_id="inv-a",
        resolved_location={"location_id": "loc-a"},
        plan=plan, create_auto_event=event,
    )
    assert result == {"applied_quantity": 5, "event_ids": ["event-b", "event-a"]}
    assert events == [("h1", "b", 3, "loc-b"), ("h1", "a", 2, "loc-a")]
    assert conn.rows["b"] == []
    assert conn.rows["a"][0]["aantal"] == 2


def test_group_stock_spread_over_distinct_locations_is_allocated_per_row(monkeypatch):
    conn = _Conn(pre_a=2, pre_b=0)
    conn.rows["b"] = [
        dict(id="b-in-1", aantal=2, space_id="kitchen", sublocation_id=None),
        dict(id="b-in-2", aantal=3, space_id="pantry", sublocation_id=None),
    ]
    plan = _plan(monkeypatch, conn, mode="consume_all_existing_before_purchase")
    assert [(p["inventory_id"], p["quantity"]) for p in plan["allocations"]] == [
        ("b-in-1", 2), ("b-in-2", 3), ("inv-a", 2),
    ]


def test_prior_purchase_location_is_protected(monkeypatch):
    conn = _Conn(pre_a=2, pre_b=0)
    conn.rows["b"] = [
        dict(id="old", aantal=4, space_id="old-shelf", sublocation_id=None),
        dict(id="today", aantal=3, space_id="new-shelf", sublocation_id=None),
    ]
    conn.purchases["b"] = 3
    # The prior purchase was actually on the new shelf.
    conn.execute_original = conn.execute
    def custom_execute(stmt, params):
        sql = str(stmt)
        if "SELECT event_type, source, quantity" in sql and params["article_id"] == "b":
            return _Result([dict(event_type="purchase", source="store_import",
                                 quantity=3, location_id="new-shelf")])
        return conn.execute_original(stmt, params)
    conn.execute = custom_execute
    plan = _plan(monkeypatch, conn, mode="consume_all_existing_before_purchase")
    assert plan is not None
    assert all(row["inventory_id"] != "today" for row in plan["allocations"])


def test_ambiguous_stock_location_falls_back(monkeypatch):
    conn = _Conn()
    conn.rows["b"].append(dict(id="extra", aantal=2, space_id="loc-b", sublocation_id=None))
    assert _plan(monkeypatch, conn) is None


def test_partial_write_raises_and_requires_transaction_rollback():
    conn = _Conn()
    conn.fail_write = True

    def event(*args, **kwargs):
        return "event-1"

    try:
        svc.apply_confirmed_synonym_deduction(
            conn, household_id="h1", purchased_article_id="a",
            purchased_quantity=2, purchase_inventory_id="inv-a",
            resolved_location={},
            plan={"purchase_day": "2026-11-10", "requested_deduction_quantity": 2,
                  "allocations": [dict(article_id="b", article_name="Melk b",
                                       inventory_id="inv-b", pre_quantity=3,
                                       space_id="loc-b", sublocation_id=None, quantity=2)]},
            create_auto_event=event,
        )
    except RuntimeError as error:
        assert "niet atomair bevestigd" in str(error)
    else:
        raise AssertionError("partial deduction must abort the transaction")


def test_confirmed_three_member_chain_quantity_mode(monkeypatch):
    conn = _Conn(pre_a=2, pre_b=3, pre_c=4)
    monkeypatch.setattr(svc, "confirmed_household_synonym_group",
                        lambda connection, household_id, article_id: ("a", "b", "c"))
    result = svc.plan_confirmed_synonym_deduction(
        conn, household_id="h1", purchased_article_id="a",
        purchase_date="2026-11-10", purchased_quantity=6,
        household_mode="consume_purchased_quantity",
        effective_mode_for_article=lambda article_id, name: "consume_purchased_quantity",
    )
    assert result["members"] == ("a", "b", "c")
    assert result["requested_deduction_quantity"] == 6
    assert [(x["article_id"], x["quantity"]) for x in result["allocations"]] == [
        ("b", 3), ("c", 3)
    ]


def test_three_member_group_all_existing_cross_location(monkeypatch):
    conn = _Conn(pre_a=2, pre_b=3, pre_c=4)
    monkeypatch.setattr(svc, "confirmed_household_synonym_group",
                        lambda connection, household_id, article_id: ("a", "b", "c"))
    result = svc.plan_confirmed_synonym_deduction(
        conn, household_id="h1", purchased_article_id="c",
        purchase_date="2026-11-10", purchased_quantity=1,
        household_mode="consume_all_existing_before_purchase",
        effective_mode_for_article=lambda article_id, name: "consume_all_existing_before_purchase",
    )
    assert result["requested_deduction_quantity"] == 9
    assert [(x["article_id"], x["quantity"]) for x in result["allocations"]] == [
        ("a", 2), ("b", 3), ("c", 4)
    ]


def test_group_cumulative_multiple_shops_preserves_today_stock(monkeypatch):
    # A first shop bought A2, consuming B2; a different shop then bought C3.
    conn = _Conn(pre_a=4, pre_b=1, pre_c=4, purchases_a=2, deducted_b=2)
    monkeypatch.setattr(svc, "confirmed_household_synonym_group",
                        lambda connection, household_id, article_id: ("a", "b", "c"))
    result = svc.plan_confirmed_synonym_deduction(
        conn, household_id="h1", purchased_article_id="c",
        purchase_date="2026-11-10", purchased_quantity=3,
        household_mode="consume_purchased_quantity",
        effective_mode_for_article=lambda article_id, name: "consume_purchased_quantity",
    )
    assert result["day_start_stock"] == 9
    assert result["prior_day_purchased_quantity"] == 2
    assert result["cumulative_day_purchased_quantity"] == 5
    assert result["requested_deduction_quantity"] == 3
    assert [(x["article_id"], x["quantity"]) for x in result["allocations"]] == [
        ("a", 2), ("b", 1)
    ]


def test_three_member_group_conflicting_override_fails_closed(monkeypatch):
    conn = _Conn(pre_a=2, pre_b=3, pre_c=4)
    monkeypatch.setattr(svc, "confirmed_household_synonym_group",
                        lambda connection, household_id, article_id: ("a", "b", "c"))
    assert svc.plan_confirmed_synonym_deduction(
        conn, household_id="h1", purchased_article_id="a",
        purchase_date="2026-11-10", purchased_quantity=3,
        household_mode="consume_purchased_quantity",
        effective_mode_for_article=lambda article_id, name:
            "none" if article_id == "c" else "consume_purchased_quantity",
    ) is None


def test_exact_package_ratio_deducts_two_half_litres_for_one_litre(monkeypatch):
    conn = _Conn(pre_a=2, pre_b=3, sizes={
        'a': (1, 'l'), 'b': (500, 'ml'), 'c': (1, 'l'),
    })
    plan = _plan(monkeypatch, conn, bought=1)
    assert plan['requested_deduction_quantity'] == 2
    assert plan['requested_equivalent_content'] == 1000
    assert plan['content_unit'] == 'volume'
    assert [(p['article_id'], p['quantity']) for p in plan['allocations']] == [('b', 2)]


def test_no_fractional_package_is_deleted_or_rounded_up(monkeypatch):
    conn = _Conn(pre_a=1, pre_b=0, sizes={
        'a': (1, 'l'), 'b': (500, 'ml'), 'c': (1, 'l'),
    })
    plan = _plan(monkeypatch, conn, new='b', bought=1)
    assert plan['requested_deduction_quantity'] == 0
    assert plan['allocations'] == []


def test_missing_or_incompatible_package_size_skips_synonym_deduction(monkeypatch):
    for sizes in (
        {'a': (1, 'l'), 'b': (1, 'stuk'), 'c': (1, 'l')},
        {'a': (None, 'l'), 'b': (500, 'ml'), 'c': (1, 'l')},
        {'a': (1, 'l'), 'b': (0, 'ml'), 'c': (1, 'l')},
    ):
        assert _plan(monkeypatch, _Conn(sizes=sizes), bought=1) is None
