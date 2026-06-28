from __future__ import annotations

from decimal import Decimal

from app.receipt_ingestion.product_candidate_gateway import append_product_candidate
from app.receipt_ingestion.spaarzegels_terms import (
    is_spaarzegels_financial_pair,
    spaarzegels_financial_metadata,
)


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _parse_quantity(value: str | None):
    if value is None or value == "":
        return None
    return Decimal(str(value).replace(",", "."))


def _parse_decimal(value: str | None):
    if value is None or value == "":
        return None
    return Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"))


def _amount_to_float(value):
    if value is None:
        return None
    return float(value)


def _classify(_value: str) -> str:
    return "product_candidate"


def test_spaarzegels_financial_pair_combines_label_and_detail_line():
    assert is_spaarzegels_financial_pair(
        label_text="Koopzegels",
        detail_text="2 x 0.10 0.20",
    )

    metadata = spaarzegels_financial_metadata(
        label_text="Koopzegels",
        detail_text="2 x 0.10 0.20",
    )

    assert metadata["line_type"] == "spaarzegels"
    assert metadata["include_in_receipt_total"] is True
    assert metadata["exclude_from_inventory"] is True
    assert metadata["external_matching_allowed"] is False


def test_gateway_preserves_quantity_unit_price_total_for_spaarzegels_pair():
    extracted: list[dict] = []

    appended_index = append_product_candidate(
        extracted,
        label="Koopzegels",
        qty_raw="2",
        amount1_raw="0.10",
        amount2_raw="0.20",
        source_index=12,
        raw_line="2 x 0.10 0.20",
        normalized_line="2 x 0.10 0.20",
        filename="jumbo-app.txt",
        store_name="Jumbo",
        function_name="_extract_savings_action_lines",
        append_branch="savings_action_line",
        parser_path="test.spaarzegels_pair",
        caller_line_hint="test spaarzegels detail pair",
        clean_label=_clean,
        parse_quantity=_parse_quantity,
        parse_decimal=_parse_decimal,
        amount_to_float=_amount_to_float,
        classify_line=_classify,
    )

    assert appended_index == 0
    assert len(extracted) == 1

    line = extracted[0]
    assert line["quantity"] == 2.0
    assert line["unit_price"] == 0.10
    assert line["line_total"] == 0.20
    assert line["line_type"] == "spaarzegels"
    assert line["include_in_receipt_total"] is True
    assert line["exclude_from_inventory"] is True
    assert line["external_matching_allowed"] is False

    trace = line["producer_trace"]
    assert trace["line_type"] == "spaarzegels"
    assert trace["external_matching_allowed"] is False


if __name__ == "__main__":
    test_spaarzegels_financial_pair_combines_label_and_detail_line()
    test_gateway_preserves_quantity_unit_price_total_for_spaarzegels_pair()
    print("SPAARZEGELS_NORMALIZATION_OK")
