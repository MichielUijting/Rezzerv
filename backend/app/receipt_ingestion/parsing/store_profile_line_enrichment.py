from __future__ import annotations

from typing import Any, Callable

from app.receipt_ingestion.parsing.line_discount_normalization import (
    should_append_generic_article_discount_cluster,
)
from app.receipt_ingestion.profiles.jumbo.app_quantity_pairs import (
    should_append_jumbo_app_quantity_detail_pair,
    should_append_jumbo_app_savings_detail_pair,
)

AppendProductCandidate = Callable[..., int | None]
CleanLabel = Callable[[str | None], str]
ParseQuantity = Callable[[str | None], Any]
ParseDecimal = Callable[[str | None], Any]
AmountToFloat = Callable[[Any], float | None]
ClassifyLine = Callable[[str], str]
NonProductLabelCheck = Callable[[str], bool]


def _append_enrichment_candidate(
    *,
    enriched: list[dict[str, Any]],
    candidate: dict[str, Any],
    filename: str | None,
    store_name: str | None,
    append_product_candidate_fn: AppendProductCandidate,
    clean_label: CleanLabel,
    parse_quantity: ParseQuantity,
    parse_decimal: ParseDecimal,
    amount_to_float: AmountToFloat,
    classify_line: ClassifyLine,
    looks_like_non_product_receipt_label: NonProductLabelCheck,
    append_branch: str,
    parser_path: str,
    caller_line_hint: str,
    confidence_score: float,
    savings_action_path: bool = False,
) -> int | None:
    return append_product_candidate_fn(
        enriched,
        label=candidate["label"],
        qty_raw=candidate["qty_raw"],
        amount1_raw=candidate["amount1_raw"],
        amount2_raw=candidate["amount2_raw"],
        source_index=candidate["source_index"],
        raw_line=candidate["raw_line"],
        normalized_line=candidate["normalized_line"],
        filename=filename,
        store_name=store_name,
        function_name="_extract_savings_action_lines" if savings_action_path else "enrich_lines_with_store_profile_pairs",
        append_branch="savings_action_line" if savings_action_path else append_branch,
        parser_path=parser_path,
        caller_line_hint=caller_line_hint,
        clean_label=clean_label,
        parse_quantity=parse_quantity,
        parse_decimal=parse_decimal,
        amount_to_float=amount_to_float,
        classify_line=classify_line,
        is_invalid_label=looks_like_non_product_receipt_label,
        confidence_score=confidence_score,
    )


def _set_discount_amount_on_appended_line(
    *,
    enriched: list[dict[str, Any]],
    appended_index: int | None,
    candidate: dict[str, Any],
    amount_to_float: AmountToFloat,
) -> None:
    if appended_index is None or appended_index < 0 or appended_index >= len(enriched):
        return
    discount_amount = candidate.get("discount_amount")
    if discount_amount is None:
        return
    enriched[appended_index]["discount_amount"] = amount_to_float(discount_amount)
    trace = enriched[appended_index].get("producer_trace")
    if isinstance(trace, dict):
        trace["discount_amount"] = amount_to_float(discount_amount)
        trace["discount_source_index"] = candidate.get("discount_source_index")
        trace["discount_raw_line"] = candidate.get("discount_raw_line")
        trace["line_total_semantics"] = "gross_line_total"
        trace["net_line_total"] = amount_to_float(
            (parse_decimal := None)  # placeholder intentionally overwritten below by caller-free float math
        )
    line_total = enriched[appended_index].get("line_total")
    try:
        net_line_total = round(float(line_total or 0) + float(discount_amount or 0), 2)
    except Exception:
        net_line_total = None
    if isinstance(trace, dict):
        trace["net_line_total"] = net_line_total


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
        article_discount_cluster = should_append_generic_article_discount_cluster(
            lines=source_lines,
            extracted=enriched,
            source_index=source_index,
            is_invalid_label=looks_like_non_product_receipt_label,
        )
        if article_discount_cluster is not None:
            appended_index = _append_enrichment_candidate(
                enriched=enriched,
                candidate=article_discount_cluster,
                filename=filename,
                store_name=store_name,
                append_product_candidate_fn=append_product_candidate_fn,
                clean_label=clean_label,
                parse_quantity=parse_quantity,
                parse_decimal=parse_decimal,
                amount_to_float=amount_to_float,
                classify_line=classify_line,
                looks_like_non_product_receipt_label=looks_like_non_product_receipt_label,
                append_branch="generic_article_discount_cluster",
                parser_path="store_profile_line_enrichment.generic_article_discount_cluster",
                caller_line_hint="generic article discount cluster via append_product_candidate",
                confidence_score=0.82,
            )
            _set_discount_amount_on_appended_line(
                enriched=enriched,
                appended_index=appended_index,
                candidate=article_discount_cluster,
                amount_to_float=amount_to_float,
            )
            continue

        jumbo_pair = should_append_jumbo_app_quantity_detail_pair(
            lines=source_lines,
            extracted=enriched,
            source_index=source_index,
            store_name=store_name,
            filename=filename,
            looks_like_non_product_receipt_label=looks_like_non_product_receipt_label,
        )
        if jumbo_pair is not None:
            _append_enrichment_candidate(
                enriched=enriched,
                candidate=jumbo_pair,
                filename=filename,
                store_name=store_name,
                append_product_candidate_fn=append_product_candidate_fn,
                clean_label=clean_label,
                parse_quantity=parse_quantity,
                parse_decimal=parse_decimal,
                amount_to_float=amount_to_float,
                classify_line=classify_line,
                looks_like_non_product_receipt_label=looks_like_non_product_receipt_label,
                append_branch="jumbo_app_quantity_detail_pair",
                parser_path="store_profile_line_enrichment.jumbo_app_quantity_detail_pair",
                caller_line_hint="store profile line enrichment via append_product_candidate",
                confidence_score=0.86,
            )
            continue

        jumbo_savings_pair = should_append_jumbo_app_savings_detail_pair(
            lines=source_lines,
            extracted=enriched,
            source_index=source_index,
            store_name=store_name,
            filename=filename,
        )
        if jumbo_savings_pair is not None:
            _append_enrichment_candidate(
                enriched=enriched,
                candidate=jumbo_savings_pair,
                filename=filename,
                store_name=store_name,
                append_product_candidate_fn=append_product_candidate_fn,
                clean_label=clean_label,
                parse_quantity=parse_quantity,
                parse_decimal=parse_decimal,
                amount_to_float=amount_to_float,
                classify_line=classify_line,
                looks_like_non_product_receipt_label=looks_like_non_product_receipt_label,
                append_branch="jumbo_app_savings_detail_pair",
                parser_path="store_profile_line_enrichment.jumbo_app_savings_detail_pair",
                caller_line_hint="store profile savings/detail pair via validated savings/action path",
                confidence_score=0.8,
                savings_action_path=True,
            )

    return enriched
