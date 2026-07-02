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
