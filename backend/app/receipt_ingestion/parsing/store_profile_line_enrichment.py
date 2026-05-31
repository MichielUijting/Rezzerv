from __future__ import annotations

from typing import Any, Callable

from app.receipt_ingestion.profiles.jumbo.app_quantity_pairs import should_append_jumbo_app_quantity_detail_pair

AppendProductCandidate = Callable[..., int | None]
CleanLabel = Callable[[str | None], str]
ParseQuantity = Callable[[str | None], Any]
ParseDecimal = Callable[[str | None], Any]
AmountToFloat = Callable[[Any], float | None]
ClassifyLine = Callable[[str], str]
NonProductLabelCheck = Callable[[str], bool]


def enrich_lines_with_store_profile_pairs(
    *,
    text_lines: list[str],
    extracted_lines: list[dict[str, Any]],
    store_name: str | None,
    filename: str | None,
    append_product_candidate_fn: AppendProductCandidate,
    clean_label: CleanLabel,
    parse_quantity: ParseQuantity,
    parse_decimal: ParseDecimal,
    amount_to_float: AmountToFloat,
    classify_line: ClassifyLine,
    looks_like_non_product_receipt_label: NonProductLabelCheck,
) -> list[dict[str, Any]]:
    """Return receipt lines enriched with safe store-profile line pairs.

    Architecture boundary:
    - diagnostics/status remain outside this layer;
    - this layer does not call OCR;
    - this layer does not read or write the database;
    - store-specific patterns stay inside profile modules;
    - appending still goes through the canonical product-candidate gateway.
    """
    enriched = [dict(line) for line in extracted_lines or []]
    source_lines = list(text_lines or [])

    for source_index, _raw_line in enumerate(source_lines):
        jumbo_pair = should_append_jumbo_app_quantity_detail_pair(
            lines=source_lines,
            extracted=enriched,
            source_index=source_index,
            store_name=store_name,
            filename=filename,
            looks_like_non_product_receipt_label=looks_like_non_product_receipt_label,
        )
        if jumbo_pair is None:
            continue

        append_product_candidate_fn(
            enriched,
            label=jumbo_pair["label"],
            qty_raw=jumbo_pair["qty_raw"],
            amount1_raw=jumbo_pair["amount1_raw"],
            amount2_raw=jumbo_pair["amount2_raw"],
            source_index=jumbo_pair["source_index"],
            raw_line=jumbo_pair["raw_line"],
            normalized_line=jumbo_pair["normalized_line"],
            filename=filename,
            store_name=store_name,
            function_name="enrich_lines_with_store_profile_pairs",
            append_branch="jumbo_app_quantity_detail_pair",
            parser_path="store_profile_line_enrichment.jumbo_app_quantity_detail_pair",
            caller_line_hint="store profile line enrichment via append_product_candidate",
            clean_label=clean_label,
            parse_quantity=parse_quantity,
            parse_decimal=parse_decimal,
            amount_to_float=amount_to_float,
            classify_line=classify_line,
            is_invalid_label=looks_like_non_product_receipt_label,
            confidence_score=0.86,
        )

    return enriched
