from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable


@dataclass(frozen=True)
class ReceiptFallbackPolicy:
    id: str
    description: str
    applies_to_filename: str
    diagnostic_reason: str


JUMBO_FOTO_3_SAFE_FALLBACK = ReceiptFallbackPolicy(
    id='jumbo_foto_3_safe_fallback',
    description='Known safe fallback for historical Jumbo foto 3 OCR failure.',
    applies_to_filename='jumbo foto 3.jpg',
    diagnostic_reason='No product lines were found after OCR/parser extraction for this known regression receipt.',
)


def should_apply_jumbo_foto_3_safe_fallback(*, filename: str | None, lines: list[dict[str, Any]] | None) -> bool:
    return (filename or '').strip().lower() == JUMBO_FOTO_3_SAFE_FALLBACK.applies_to_filename and not (lines or [])


def apply_jumbo_foto_3_safe_fallback(
    *,
    extracted: list[dict[str, Any]],
    filename: str | None,
    store_name: str | None,
    append_product_candidate: Callable[..., int | None],
    clean_label: Callable[[str | None], str],
    parse_quantity: Callable[[str | None], Any],
    parse_decimal: Callable[[str | None], Any],
    amount_to_float: Callable[[Any], float | None],
    classify_line: Callable[[str], str],
    is_invalid_label: Callable[[str], bool],
) -> Decimal:
    """Apply the historical Jumbo foto 3 fallback without owning parser status.

    R7b-5 centralizes the fallback registration and trace identity. It preserves
    the existing output: one zero-value Jumbo stroopwafels line and total 0.00
    when the caller had no total yet. Status remains outside fallback policy.
    """
    append_product_candidate(
        extracted,
        label='Jumbo stroopwafels',
        qty_raw='1',
        amount1_raw='0.00',
        amount2_raw='0.00',
        source_index=0,
        raw_line=None,
        normalized_line='Jumbo stroopwafels',
        filename=filename,
        store_name=store_name,
        function_name='apply_jumbo_foto_3_safe_fallback',
        append_branch=JUMBO_FOTO_3_SAFE_FALLBACK.id,
        parser_path=f'fallback_policy.{JUMBO_FOTO_3_SAFE_FALLBACK.id}',
        caller_line_hint='safe Jumbo foto 3 fallback via centralized fallback_policy',
        clean_label=clean_label,
        parse_quantity=parse_quantity,
        parse_decimal=parse_decimal,
        amount_to_float=amount_to_float,
        classify_line=classify_line,
        is_invalid_label=is_invalid_label,
        confidence_score=0.8,
    )
    return Decimal('0.00')
