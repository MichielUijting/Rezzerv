"""PR6: complete household-owned cadence + observed purchase volume.

Pure projections, no separate database or inventory mutation.
"""
from datetime import date
import json

import pytest

from app.services.almost_out_historical_cadence import (
    load_confirmed_purchase_cadences,
    prediction_from_confirmed_cadence,
)


def cadence(ids=("article-ah",), interval=10, count=2, last=date(2026, 11, 20)):
    return {
        "members": tuple(ids),
        "interval_days": interval,
        "purchase_day_count": count,
        "last_date": last,
        "first_date": date(2026, 11, 10),
    }


def event(article, day, quantity, kind="purchase"):
    return {
        "article_id": article,
        "purchase_date": day,
        "quantity": quantity,
        "event_type": kind,
    }


def test_single_historical_repeat_and_one_current_purchase_quantity_forecast():
    row = cadence()
    result = prediction_from_confirmed_cadence(
        row, [event("article-ah", "2026-11-20", 2)],
        7, current_quantity=1, minimum_stock=0,
        member_article_ids=["article-ah"], now=date(2026, 11, 21),
    )
    assert result["prediction_available"]
    assert result["prediction_triggered"] is True
    assert result["purchase_event_count"] == 2
    assert result["average_purchase_interval_days"] == 10
    assert result["predicted_quantity_at_horizon"] == pytest.approx(-0.4)
    assert result["estimated_consumption_per_day"] == pytest.approx(0.2)
    assert result["average_purchase_quantity"] is None


def test_confirmed_synonyms_combine_exact_member_quantities_one_day():
    row = cadence(("article-ah", "article-lidl"), interval=20)
    result = prediction_from_confirmed_cadence(
        row, [
            event("article-ah", "2026-11-20", 1),
            event("article-lidl", "2026-11-20", 1),
            event("article-other", "2026-11-20", 1000),
        ], 15, current_quantity=3, minimum_stock=1,
        member_article_ids=["article-ah", "article-lidl"],
        now=date(2026, 11, 21),
    )
    assert result["observed_latest_purchase_quantity"] == 2
    assert result["predicted_quantity_at_horizon"] == pytest.approx(1.5)
    assert result["prediction_triggered"] is False


@pytest.mark.parametrize("updates", [
    {"member_article_ids": ["article-other"]},
    {"member_article_ids": ["article-ah", "article-other"]},
    {"current_quantity": -1},
    {"current_quantity": float("nan")},
    {"prediction_days": 0},
    {"minimum_stock": -1},
    {"now": date(2026, 11, 19)},
])
def test_incomplete_invalid_or_wrong_scope_never_forecasts(updates):
    values = {
        "cadence": cadence(), "purchase_events": [event("article-ah", "2026-11-20", 1)],
        "prediction_days": 7, "current_quantity": 1, "minimum_stock": 0,
        "member_article_ids": ["article-ah"], "now": date(2026, 11, 21),
    }
    values.update(updates)
    row = prediction_from_confirmed_cadence(
        values["cadence"], values["purchase_events"], values["prediction_days"],
        current_quantity=values["current_quantity"],
        minimum_stock=values["minimum_stock"],
        member_article_ids=values["member_article_ids"], now=values["now"],
    )
    assert row is None


def test_one_day_or_history_without_actual_quantity_never_creates_signal():
    assert prediction_from_confirmed_cadence(
        cadence(count=1), [event("article-ah", "2026-11-20", 1)],
        7, current_quantity=1, member_article_ids=["article-ah"],
    ) is None
    assert prediction_from_confirmed_cadence(
        cadence(), [], 7, current_quantity=1, member_article_ids=["article-ah"],
    ) is None
    assert prediction_from_confirmed_cadence(
        cadence(), [event("article-ah", "2026-11-20", 1, "baseline")],
        7, current_quantity=1, member_article_ids=["article-ah"],
    ) is None


def test_later_unaccounted_purchase_blocks_stale_cadence():
    assert prediction_from_confirmed_cadence(
        cadence(), [
            event("article-ah", "2026-11-20", 1),
            event("article-ah", "2026-11-22", 5),
        ], 7, current_quantity=1, member_article_ids=["article-ah"],
        now=date(2026, 11, 24),
    ) is None


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _Conn:
    class Dialect:
        name = "postgresql"
    dialect = Dialect()

    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def execute(self, statement, params):
        sql = str(statement)
        assert sql.lstrip().upper().startswith("SELECT")
        assert "WHERE c.household_id = :household_id" in sql
        assert "ha.household_id = c.household_id" in sql
        assert "COALESCE(ha.status, 'active') = 'active'" in sql
        assert params["household_id"] == "household-a"
        assert params["article_ids"] == sorted(["article-ah", "article-lidl"])
        self.queries.append(sql)
        return _Rows(self.rows)


def db_row(article, members=("article-ah", "article-lidl"), interval=10):
    return {
        "household_article_id": article,
        "average_repurchase_interval_days": interval,
        "purchase_day_count": 2,
        "first_purchase_date": date(2026, 11, 10),
        "last_purchase_date": date(2026, 11, 20),
        "matched_and_synonyms": json.dumps(members),
    }


def test_confirmed_members_require_complete_consistent_active_household_group():
    conn = _Conn([db_row("article-ah"), db_row("article-lidl")])
    articles = [{"id": "article-ah"}, {"id": "article-lidl"}]
    result = load_confirmed_purchase_cadences(conn, "household-a", articles)
    assert set(result) == {"article-ah", "article-lidl"}
    assert result["article-ah"]["members"] == ("article-ah", "article-lidl")
    assert len(conn.queries) == 1

    missing = _Conn([db_row("article-ah")])
    assert load_confirmed_purchase_cadences(missing, "household-a", articles) == {}
    inconsistent = _Conn([db_row("article-ah"), db_row("article-lidl", interval=9)])
    assert load_confirmed_purchase_cadences(inconsistent, "household-a", articles) == {}
    inactive = _Conn([db_row("article-ah"), db_row("article-lidl")])
    assert load_confirmed_purchase_cadences(
        inactive, "household-a",
        [{"id": "article-ah"}, {"id": "article-lidl", "status": "inactive"}],
    ) == {}


def test_no_cadence_query_for_legacy_or_non_postgresql_connection():
    class Legacy:
        dialect = type("Dialect", (), {"name": "sqlite"})()
        def execute(self, *_args):
            raise AssertionError("Legacy connection must not be queried")
    assert load_confirmed_purchase_cadences(Legacy(), "household-a", [{"id": "a"}]) == {}
    assert load_confirmed_purchase_cadences(_Conn([]), "0", [{"id": "article-ah"}]) == {}
