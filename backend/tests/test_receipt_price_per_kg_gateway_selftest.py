from app.receipt_ingestion.line_classifier import trace_receipt_text_line_classification
from app.receipt_ingestion.product_candidate_gateway import append_product_candidate


def clean_label(value):
    return str(value or "").strip()


def parse_quantity(value):
    if not value:
        return None
    return float(str(value).replace(",", "."))


def parse_decimal(value):
    if value is None or value == "":
        return None
    return float(str(value).replace(",", "."))


def amount_to_float(value):
    return None if value is None else float(value)


def classify_line(line):
    return trace_receipt_text_line_classification(line).get("classification")


def trace_line(line):
    return trace_receipt_text_line_classification(line)


def check_prijs_per_kg_product_label_is_preserved_by_gateway():
    extracted = []

    idx = append_product_candidate(
        extracted,
        label="Prijs per kg KOMKOMMER",
        qty_raw=None,
        amount1_raw="11,97",
        amount2_raw="0,99",
        source_index=1,
        raw_line="Prijs per kg KOMKOMMER 11,97 0,99",
        normalized_line="Prijs per kg KOMKOMMER 11,97 0,99",
        filename="AH foto 11.jpeg",
        store_name="Albert Heijn",
        function_name="_extract_ah_lines",
        append_branch="label_first",
        parser_path="ah_photo",
        caller_line_hint="prijs_per_kg_product_label",
        clean_label=clean_label,
        parse_quantity=parse_quantity,
        parse_decimal=parse_decimal,
        amount_to_float=amount_to_float,
        classify_line=classify_line,
        trace_line=trace_line,
    )

    assert idx == 0
    assert len(extracted) == 1
    assert extracted[0]["normalized_label"] == "KOMKOMMER"
    assert extracted[0]["line_total"] == 0.99
    assert extracted[0]["producer_trace"]["supporting_amount_prefix_normalization_applied"] is True


def run_checks():
    check_prijs_per_kg_product_label_is_preserved_by_gateway()
    print("PASS check_prijs_per_kg_product_label_is_preserved_by_gateway")
    print("RESULT: 1 gateway price-per-kg product-label check passed")


if __name__ == "__main__":
    run_checks()
