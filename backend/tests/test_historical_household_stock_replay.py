"""PR3 pure replay contracts; no DB, Docker or user-facing action required."""
from datetime import date

import pytest

from app.services.historical_household_stock_replay import replay_historical_stock

CUTOFF = date(2026, 11, 20)
NONE = "none"
MATCH = "consume_purchased_quantity"
RESET = "consume_all_existing_before_purchase"


def receipt(day, quantity, *, line, article="h-a", house="home1",
            sha=None, receipt_id=None):
    return {
        "household_id": house,
        "household_article_id": article,
        "purchase_date": day,
        "quantity": quantity,
        "receipt_id": receipt_id or line,
        "line_id": line,
        "raw_sha": sha or ("sha-" + line),
    }


def replay(lines, modes, groups=None, factors=None):
    return replay_historical_stock(
        household_id="home1", cutoff=CUTOFF, purchases=lines,
        modes=modes, synonym_groups=groups, package_sizes=factors,
    )


@pytest.mark.parametrize("mode,expected", [
    (NONE, 7),
    (MATCH, 4),
    (RESET, 4),
])
def test_three_household_modes_same_canonical_article(mode, expected):
    lines = [
        receipt("2026-09-01", 2, line="first"),
        receipt("2026-10-01", 1, line="second"),
        receipt("2026-11-10", 4, line="third"),
    ]
    assert replay(list(reversed(lines)), {"h-a": mode})["quantities"] == {"h-a": expected}


def test_quantity_consumption_may_leave_more_than_new_purchase():
    events = [
        receipt("2026-11-01", 10, line="a"),
        receipt("2026-11-03", 2, line="b"),
    ]
    assert replay(events, {"h-a": MATCH})["quantities"]["h-a"] == 10


def test_same_day_multiple_shops_are_one_product_day():
    events = [
        receipt("2026-11-01", 5, line="a"),
        receipt("2026-11-03", 2, line="ah"),
        receipt("2026-11-03", 3, line="lidl"),
    ]
    assert replay(events, {"h-a": RESET})["quantities"]["h-a"] == 5
    assert replay(events, {"h-a": MATCH})["quantities"]["h-a"] == 5
    assert replay(events, {"h-a": NONE})["quantities"]["h-a"] == 10


def test_same_receipt_duplicate_sha_never_counts_twice():
    events = [
        receipt("2026-11-01", 5, line="one", sha="same", receipt_id="receipt-first"),
        receipt("2026-11-01", 5, line="copy", sha="same", receipt_id="receipt-copy"),
    ]
    result = replay(events, {"h-a": NONE})
    assert result["quantities"]["h-a"] == 5
    assert result["excluded_duplicate_receipt_lines"] == 1


def test_distinct_lines_of_same_receipt_sha_are_counted():
    events = [
        receipt("2026-11-01", 5, line="one", sha="same", receipt_id="receipt-1"),
        receipt("2026-11-01", 2, line="two", sha="same", receipt_id="receipt-1"),
    ]
    assert replay(events, {"h-a": NONE})["quantities"]["h-a"] == 7


def test_confirmed_synonym_group_reset_keeps_only_last_day_stock():
    group = {"h-a": ("h-a", "h-b"), "h-b": ("h-a", "h-b")}
    events = [
        receipt("2026-11-01", 5, line="coffee", article="h-a"),
        receipt("2026-11-10", 2, line="coffee2", article="h-b"),
    ]
    result = replay(events, {"h-a": RESET, "h-b": RESET}, group,
                    {"h-a": 1, "h-b": 1})
    assert result["quantities"] == {"h-a": 0, "h-b": 2}


def test_synonym_quantity_deducts_proven_equal_content_only():
    group = {"h-a": ("h-a", "h-b"), "h-b": ("h-a", "h-b")}
    events = [
        receipt("2026-11-01", 3, line="litre", article="h-a"),
        receipt("2026-11-10", 2, line="half", article="h-b"),
    ]
    # One 1-litre product is exactly two half-litre packages.
    result = replay(events, {"h-a": MATCH, "h-b": MATCH}, group,
                    {"h-a": 1000, "h-b": 500})
    assert result["quantities"] == {"h-a": 2, "h-b": 2}


def test_synonym_partial_packages_are_not_rounded_up():
    group = {"h-a": ("h-a", "h-b"), "h-b": ("h-a", "h-b")}
    events = [
        receipt("2026-11-01", 1, line="litre", article="h-a"),
        receipt("2026-11-10", 1, line="half", article="h-b"),
    ]
    result = replay(events, {"h-a": MATCH, "h-b": MATCH}, group,
                    {"h-a": 1000, "h-b": 500})
    assert result["quantities"] == {"h-a": 1, "h-b": 1}


def test_conflicting_article_overrides_fail_closed_for_synonyms():
    lines = [receipt("2026-11-01", 2, line="a")]
    with pytest.raises(ValueError, match="afwijkende artikelinstellingen"):
        replay(lines, {"h-a": RESET, "h-b": NONE},
               {"h-a": ("h-a", "h-b"), "h-b": ("h-a", "h-b")},
               {"h-a": 1, "h-b": 1})


@pytest.mark.parametrize("bad", [
    receipt("2026-11-01", 1, line="foreign", house="home2"),
    receipt("2026-11-20", 1, line="current"),
    receipt("2026-11-01", 0, line="zero"),
    receipt("2026-11-01", 1.5, line="fraction"),
    receipt("2026-11-01", 1, line="no-sha", sha=""),
])
def test_untrusted_or_current_rows_fail_closed(bad):
    if bad["line_id"] == "no-sha":
        bad["raw_sha"] = ""
    with pytest.raises(ValueError):
        replay([bad], {"h-a": NONE})


def test_unknown_article_mode_and_group_size_fail_closed():
    with pytest.raises(ValueError):
        replay([receipt("2026-11-01", 1, line="x")], {})
    with pytest.raises(ValueError):
        replay(
            [receipt("2026-11-01", 1, line="x")],
            {"h-a": RESET, "h-b": RESET},
            {"h-a": ("h-a", "h-b"), "h-b": ("h-a", "h-b")},
            {"h-a": 1},
        )


def test_nonconsumable_articles_follow_disabled_mode():
    lines = [
        receipt("2026-11-01", 2, line="first"),
        receipt("2026-11-10", 3, line="second"),
    ]
    assert replay(lines, {"h-a": NONE})["quantities"]["h-a"] == 5


def test_chronological_order_is_invariant():
    lines = [
        receipt("2026-10-01", 2, line="1"),
        receipt("2026-11-10", 3, line="3"),
        receipt("2026-10-29", 6, line="2"),
    ]
    assert replay(lines, {"h-a": MATCH}) == replay(list(reversed(lines)), {"h-a": MATCH})


def test_three_purchase_days_provide_average_repurchase_interval():
    lines = [
        receipt("2026-09-01", 2, line="lidl-1"),
        receipt("2026-10-01", 1, line="ah-2"),
        receipt("2026-11-01", 3, line="jumbo-3"),
        receipt("2026-11-01", 2, line="ah-4"),
    ]
    result = replay(list(reversed(lines)), {"h-a": RESET})
    evidence = result["purchase_cadences"]["h-a"]
    assert evidence["purchase_day_count"] == 3
    assert evidence["average_repurchase_interval_days"] == 30.5
    assert evidence["first_purchase_date"] == "2026-09-01"
    assert evidence["last_purchase_date"] == "2026-11-01"
    assert result["quantities"]["h-a"] == 5
    assert result["source_fingerprint"] == replay(lines, {"h-a": RESET})["source_fingerprint"]


def test_confirmed_synonyms_share_same_purchase_interval_without_duplicate_days():
    group = {"h-a": ("h-a", "h-b"), "h-b": ("h-a", "h-b")}
    lines = [
        receipt("2026-09-01", 1, line="1", article="h-a"),
        receipt("2026-10-01", 2, line="2", article="h-b"),
        receipt("2026-11-01", 1, line="3", article="h-a"),
        receipt("2026-11-01", 2, line="4", article="h-b"),
    ]
    result = replay(lines, {"h-a": RESET, "h-b": RESET}, group,
                    {"h-a": 1000, "h-b": 500})
    assert result["quantities"] == {"h-a": 1, "h-b": 2}
    a = result["purchase_cadences"]["h-a"]
    b = result["purchase_cadences"]["h-b"]
    assert a == b
    assert a["purchase_day_count"] == 3
    assert a["average_repurchase_interval_days"] == 30.5
    assert a["matched_and_synonyms"] == ["h-a", "h-b"]


def test_group_member_without_own_purchase_inherits_confirmed_cadence_and_zero_stock():
    group = {"h-a": ("h-a", "h-b"), "h-b": ("h-a", "h-b")}
    lines = [
        receipt("2026-09-01", 1, line="1"),
        receipt("2026-10-01", 1, line="2"),
        receipt("2026-11-01", 1, line="3"),
    ]
    result = replay(lines, {"h-a": RESET, "h-b": RESET}, group,
                    {"h-a": 1000, "h-b": 500})
    assert result["quantities"] == {"h-a": 1, "h-b": 0}
    assert result["purchase_cadences"]["h-a"] == result["purchase_cadences"]["h-b"]


@pytest.mark.parametrize("days", [
    ("2026-11-01", "2026-11-02", "2026-11-03"),
    ("2026-02-01", "2026-03-01", "2026-04-01"),
    ("2026-01-01", "2026-10-01", "2026-11-01"),
])
def test_no_unsupported_or_unrepresentative_cadence(days):
    lines = [receipt(day, 1, line=str(i)) for i, day in enumerate(days)]
    assert replay(lines, {"h-a": RESET})["purchase_cadences"] == {}


def test_group_two_distinct_purchase_days_cannot_claim_average_interval():
    group = {"h-a": ("h-a", "h-b"), "h-b": ("h-a", "h-b")}
    lines = [
        receipt("2026-10-01", 1, line="1", article="h-a"),
        receipt("2026-11-01", 1, line="2", article="h-b"),
    ]
    result = replay(lines, {"h-a": RESET, "h-b": RESET}, group,
                    {"h-a": 1000, "h-b": 500})
    assert result["purchase_cadences"] == {}
