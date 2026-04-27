"""Receipt line extraction and line-quality helpers.

Compatibility façade: Release 0 re-exports the existing implementation from
``app.services.receipt_service``. Later releases can move code here without
changing API imports again.
"""

from ....services.receipt_service import (  # noqa: F401
    _amount_to_float,
    _clean_receipt_label,
    _discount_decimal_total,
    _discount_or_free_total_zero_case,
    _extract_receipt_lines,
    _extract_sparse_receipt_lines,
    _filter_non_product_receipt_lines,
    _is_invalid_aldi_article_candidate,
    _line_decimal_total,
    _looks_like_aldi_payment_line,
    _looks_like_aldi_vat_summary_line,
    _looks_like_item_label_only,
    _looks_like_non_product_receipt_label,
    _normalize_text_lines,
    _parse_decimal,
    _parse_quantity,
    _receipt_line_financials,
    _should_skip_receipt_line,
    _totals_match_receipt_lines,
)
