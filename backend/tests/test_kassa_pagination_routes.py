"""Focused, read-only tests for the Kassa page projection."""
from datetime import datetime

from app.api.kassa_pagination_routes import _page_payload


def _row(receipt_id, *, store="Albert Heijn", amount=12.0, sha="", status="approved"):
    return {
        "receipt_table_id": receipt_id,
        "raw_receipt_id": receipt_id,
        "store_name": store,
        "purchase_at": "2026-11-17T11:00:00",
        "created_at": datetime(2026, 11, 17, 11, 0),
        "total_amount": amount,
        "currency": "EUR",
        "line_count": 1,
        "line_total_sum": amount,
        "net_line_total_sum": amount,
        "line_discount_sum": 0,
        "discount_total": 0,
        "parse_status": status,
        "source_label": "Manual upload",
        "sha256_hash": sha,
    }


def test_page_is_ten_rows_and_count_covers_all():
    rows = [_row(str(i), store=f"Winkel {i}") for i in range(25)]
    data = _page_payload(rows, page=2, page_size=10)
    assert data["total"] == 25
    assert len(data["items"]) == 10
    assert len({row["receipt_table_id"] for row in data["items"]}) == 10
    assert data["counts"]["Gecontroleerd"] == 25
    assert data["counts"]["Controle nodig"] == 0


def test_deduplication_and_filters_do_not_stop_at_first_page():
    rows = [_row(str(i), store=f"Winkel {i}") for i in range(24)]
    rows[0]["sha256_hash"] = "same-source"
    rows[1]["sha256_hash"] = "same-source"
    rows[-1]["store_name"] = "Doelwinkel"
    results = _page_payload(rows, page=1, page_size=10, winkel="doelwinkel")
    assert results["total"] == 1
    assert results["items"][0]["receipt_table_id"] == "23"
    assert results["counts"]["Gecontroleerd"] == 23


def test_review_status_is_from_production_status_service_not_client():
    rows = [_row("checked"), _row("review", store="Reviewwinkel")]
    rows[1]["store_name"] = ""
    result = _page_payload(rows, page=1, page_size=10, status="Controle nodig")
    assert result["total"] == 1
    assert result["items"][0]["receipt_table_id"] == "review"
    assert result["items"][0]["inbox_status"] == "Controle nodig"
    assert result["counts"]["Gecontroleerd"] == 1


def test_filter_and_sort_use_all_rows():
    rows = [_row(str(i), store=f"Winkel {i}", amount=100 - i) for i in range(22)]
    data = _page_payload(rows, page=1, page_size=10, sort_key="total", sort_direction="asc")
    assert [x["receipt_table_id"] for x in data["items"]][:3] == ["21", "20", "19"]
    assert _page_payload(rows, page=1, page_size=10, artikelen="1")["total"] == 22


def test_mobile_search_matches_shop_or_canonical_status():
    rows = [_row("first", store="AH"), _row("second", store="Jumbo")]
    result = _page_payload(rows, page=1, page_size=10, zoek="jumbo")
    assert result["total"] == 1
    assert result["items"][0]["receipt_table_id"] == "second"
    result = _page_payload(rows, page=1, page_size=10, zoek="gecontroleerd")
    assert result["total"] == 2


def test_timezone_date_filter_is_local_to_client():
    rows = [_row("one", store="AH")]
    assert _page_payload(rows, page=1, page_size=10, datum="17-11-2026")["total"] == 1
    assert _page_payload(rows, page=1, page_size=10, datum="16-11-2026")["total"] == 0
