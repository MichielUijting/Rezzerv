from __future__ import annotations

from app.services.product_day_auto_consume_service import (
    AUTO_CONSUME_ALL_EXISTING,
    AUTO_CONSUME_NONE,
    AUTO_CONSUME_PURCHASED_QUANTITY,
    compute_product_day_auto_deduction,
)


class _FakeMappings:
    def __init__(self, row):
        self._row = row

    def one(self):
        return dict(self._row)


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return _FakeMappings(self._row)


class _FakeConnection:
    def __init__(self, row=None):
        self.row = row or {
            "purchased_quantity": 0,
            "auto_consumed_quantity": 0,
            "first_purchase_old_quantity": None,
        }
        self.execute_count = 0
        self.last_params = None
        self.last_statement = ""

    def execute(self, statement, params):
        self.execute_count += 1
        self.last_statement = str(statement)
        self.last_params = dict(params)
        return _FakeResult(self.row)


def _decision(
    row=None,
    *,
    mode: str,
    pre: int,
    purchased: int,
    purchase_date: str = "2026-08-26",
    household: str = "h1",
    article: str = "a1",
):
    conn = _FakeConnection(row)
    result = compute_product_day_auto_deduction(
        conn,
        household_id=household,
        household_article_id=article,
        purchase_date=purchase_date,
        mode=mode,
        pre_purchase_total=pre,
        purchased_quantity=purchased,
    )
    return conn, result


def test_first_purchase_keeps_existing_semantics():
    conn, result = _decision(
        mode=AUTO_CONSUME_PURCHASED_QUANTITY,
        pre=10,
        purchased=2,
    )
    assert result["product_day_applied"] is True
    assert result["day_start_stock"] == 10
    assert result["requested_deduction_quantity"] == 2
    assert conn.execute_count == 1


def test_second_same_day_purchase_is_cumulative():
    _, result = _decision(
        {
            "purchased_quantity": 2,
            "auto_consumed_quantity": 2,
            "first_purchase_old_quantity": 10,
        },
        mode=AUTO_CONSUME_PURCHASED_QUANTITY,
        pre=10,
        purchased=3,
    )
    assert result["prior_day_purchased_quantity"] == 2
    assert result["prior_day_auto_consumed_quantity"] == 2
    assert result["cumulative_day_purchased_quantity"] == 5
    assert result["requested_deduction_quantity"] == 3


def test_purchased_quantity_stops_when_day_start_stock_is_exhausted():
    _, result = _decision(
        {
            "purchased_quantity": 3,
            "auto_consumed_quantity": 3,
            "first_purchase_old_quantity": 4,
        },
        mode=AUTO_CONSUME_PURCHASED_QUANTITY,
        pre=4,
        purchased=3,
    )
    assert result["requested_deduction_quantity"] == 1


def test_all_existing_is_consumed_only_once_per_product_day():
    _, result = _decision(
        {
            "purchased_quantity": 2,
            "auto_consumed_quantity": 5,
            "first_purchase_old_quantity": 5,
        },
        mode=AUTO_CONSUME_ALL_EXISTING,
        pre=2,
        purchased=3,
    )
    assert result["day_start_stock"] == 5
    assert result["requested_deduction_quantity"] == 0


def test_new_day_with_no_prior_day_events_starts_fresh():
    _, result = _decision(
        mode=AUTO_CONSUME_PURCHASED_QUANTITY,
        pre=8,
        purchased=2,
        purchase_date="2026-08-27",
    )
    assert result["prior_day_purchased_quantity"] == 0
    assert result["prior_day_auto_consumed_quantity"] == 0
    assert result["day_start_stock"] == 8
    assert result["requested_deduction_quantity"] == 2


def test_query_scope_is_household_article_and_receipt_day():
    conn, result = _decision(
        mode=AUTO_CONSUME_ALL_EXISTING,
        pre=6,
        purchased=2,
        household="household-A",
        article="article-A",
        purchase_date="2026-08-26T21:15:00+02:00",
    )
    assert result["purchase_day"] == "2026-08-26"
    assert conn.last_params == {
        "household_id": "household-A",
        "household_article_id": "article-A",
        "purchase_day": "2026-08-26",
    }
    assert "household_id = :household_id" in conn.last_statement
    assert "household_article_id = :household_article_id" in conn.last_statement


def test_iso_timestamp_uses_receipt_calendar_day():
    _, result = _decision(
        {
            "purchased_quantity": 2,
            "auto_consumed_quantity": 2,
            "first_purchase_old_quantity": 5,
        },
        mode=AUTO_CONSUME_PURCHASED_QUANTITY,
        pre=5,
        purchased=1,
        purchase_date="2026-08-26T21:15:00+02:00",
    )
    assert result["purchase_day"] == "2026-08-26"
    assert result["requested_deduction_quantity"] == 1


def test_backdated_same_day_purchase_extends_existing_group():
    _, result = _decision(
        {
            "purchased_quantity": 3,
            "auto_consumed_quantity": 3,
            "first_purchase_old_quantity": 10,
        },
        mode=AUTO_CONSUME_PURCHASED_QUANTITY,
        pre=10,
        purchased=2,
        purchase_date="2026-08-26T09:00:00+02:00",
    )
    assert result["day_start_stock"] == 10
    assert result["cumulative_day_purchased_quantity"] == 5
    assert result["requested_deduction_quantity"] == 2


def test_invalid_purchase_date_falls_back_without_database_read():
    conn, result = _decision(
        mode=AUTO_CONSUME_ALL_EXISTING,
        pre=5,
        purchased=2,
        purchase_date="26-08-2026",
    )
    assert result["product_day_applied"] is False
    assert result["requested_deduction_quantity"] == 5
    assert conn.execute_count == 0


def test_none_mode_never_consumes():
    _, result = _decision(
        {
            "purchased_quantity": 4,
            "auto_consumed_quantity": 0,
            "first_purchase_old_quantity": 9,
        },
        mode=AUTO_CONSUME_NONE,
        pre=9,
        purchased=4,
    )
    assert result["requested_deduction_quantity"] == 0
