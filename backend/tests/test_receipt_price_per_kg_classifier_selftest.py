from app.receipt_ingestion.line_classifier import trace_receipt_text_line_classification


def run_checks():
    pure = trace_receipt_text_line_classification("Prijs per kg")
    amount_only = trace_receipt_text_line_classification("Prijs per kg 2,29")
    product = trace_receipt_text_line_classification("Prijs per kg KOMKOMMER 11,97 0,99")

    assert pure["classification"] == "amount_detail", pure
    assert amount_only["classification"] == "amount_detail", amount_only
    assert product["classification"] != "amount_detail", product

    print("PASS check_price_per_kg_product_suffix_is_not_amount_detail")
    print("RESULT: 1 classifier price-per-kg product-suffix check passed")


if __name__ == "__main__":
    run_checks()
