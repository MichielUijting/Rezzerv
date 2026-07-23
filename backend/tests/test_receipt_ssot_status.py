from app.services.receipt_ssot_status import apply_po_norm_status, load_po_norm_status_items


def test_non_baseline_receipt_with_matching_totals_is_controlled():
    payload = {
        "id": "not-in-baseline",
        "store_name": "Lidl",
        "total_amount": 33.80,
        "line_count": 11,
        "line_total_sum": 33.80,
        "net_line_total_sum": 33.80,
        "parse_status": "approved",
    }

    result = apply_po_norm_status(payload)

    assert result["po_norm_status_label"] == "Gecontroleerd"
    assert result["po_norm_status"] == "controlled"
    assert "NO_BASELINE_MATCH" not in result["po_norm_failed_criteria"]
    assert "parse_status" not in result


def test_line_sum_mismatch_still_requires_review():
    payload = {
        "id": "content-error",
        "store_name": "Lidl",
        "total_amount": 33.80,
        "line_count": 11,
        "line_total_sum": 31.80,
        "net_line_total_sum": 31.80,
    }

    result = apply_po_norm_status(payload)

    assert result["po_norm_status_label"] == "Controle nodig"
    assert "LINE_SUM_TOTAL_MISMATCH" in result["po_norm_failed_criteria"]


def test_baseline_loader_is_not_used_for_production_status():
    assert load_po_norm_status_items() == {}

def test_line_discounts_are_part_of_functional_net_line_total():
    from decimal import Decimal

    unit = Decimal("1")

    payload_from_sums = {
        "store_name": "GenericChain",
        "total_amount": unit,
        "line_count": 1,
        "line_total_sum": unit + unit,
        "line_discount_sum": -unit,
    }

    result_from_sums = apply_po_norm_status(payload_from_sums)

    assert result_from_sums["po_norm_status_label"] == "Gecontroleerd"
    assert result_from_sums["po_norm_failed_criteria"] == []

    payload_from_lines = {
        "store_name": "GenericChain",
        "total_amount": unit,
        "line_count": 1,
        "lines": [
            {
                "line_total": unit + unit,
                "discount_amount": -unit,
                "is_deleted": 0,
            }
        ],
    }

    result_from_lines = apply_po_norm_status(payload_from_lines)

    assert result_from_lines["po_norm_status_label"] == "Gecontroleerd"
    assert result_from_lines["po_norm_failed_criteria"] == []

def test_receipt_status_accepts_either_line_or_receipt_discount_without_double_counting():
    payload = {
        "store_name": "Albert Heijn",
        "total_amount": "25.11",
        "line_count": 11,
        "line_total_sum": "27.61",
        "line_discount_sum": "-2.50",
        "discount_total": "-2.50",
    }

    result = apply_po_norm_status(payload)

    assert result["po_norm_status_label"] == "Gecontroleerd"
    assert result["po_norm_failed_criteria"] == []

