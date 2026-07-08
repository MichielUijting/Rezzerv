"""PLUS bbox activation readiness diagnostics.

Diagnose-only module.

Purpose:
- decide whether PLUS bbox reconstruction is safe enough for possible guarded runtime activation;
- require exact financial closure;
- block footer/payment/tax contamination in reconstructed article rows;
- block missing subtotal/total;
- block suspicious unused fragments unless they are harmless noise;
- do not alter parser output or database state.

No hardcoded article names, receipt IDs, filenames or receipt-specific prices.
"""

from __future__ import annotations

import re
from typing import Any

from app.receipt_ingestion.parsing.plus_non_article_financial_corrections import (
    diagnose_plus_non_article_financial_corrections,
)


_BLOCKED_ARTICLE_TEXT_RE = re.compile(
    r'\b(?:'
    r'pin|btw|contactless|contactiess|klantticket|terminal|merchant|poi|'
    r'transactie|autorisatie|kaart|kaartserienummer|betaling|wisselgeld|'
    r'leesmethode|maestro|v[\-\s]?pay|par:|eur|incl\.?|btw\s+groep|'
    r'openingstijden|prettige|bonnr|www\.|u\s+bent\s+geholpen'
    r')\b',
    re.IGNORECASE,
)

_ALLOWED_UNUSED_NOISE_RE = re.compile(
    r'^(?:'
    r'[*.=\-\s]+|'
    r'assa|'
    r'.{0,2}|'
    r'.*\b(?:inclusief\s+korting|spaarkaart|geregistreerd)\b.*'
    r')$',
    re.IGNORECASE,
)

_SUSPICIOUS_UNUSED_RE = re.compile(
    r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}',
    re.IGNORECASE,
)


def _normalize(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _article_blocker_reasons(article_rows: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []

    for index, row in enumerate(article_rows, start=1):
        line = _normalize(row.get('reconstructed_line'))
        if not line:
            reasons.append(f'article_row_{index}_empty')
            continue

        if _BLOCKED_ARTICLE_TEXT_RE.search(line):
            reasons.append(f'article_row_{index}_contains_footer_payment_or_tax_text:{line}')

    return reasons


def _unused_fragment_reasons(unused_fragments: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []

    for fragment in unused_fragments or []:
        text = _normalize(fragment.get('text'))
        if not text:
            continue

        if _ALLOWED_UNUSED_NOISE_RE.match(text):
            continue

        if _SUSPICIOUS_UNUSED_RE.search(text):
            reasons.append(f'suspicious_unused_text:{text}')

    return reasons


def diagnose_plus_bbox_activation_readiness(
    texts: list[Any],
    boxes: list[Any],
    runtime_lines: list[str],
) -> dict[str, Any]:
    diag = diagnose_plus_non_article_financial_corrections(texts, boxes, runtime_lines)

    reasons: list[str] = []

    article_rows = list(diag.get('article_rows') or [])
    unused_text_fragments = list(diag.get('unused_text_fragments') or [])
    unused_unit_fragments = list(diag.get('unused_unit_fragments') or [])

    if not diag.get('exact_subtotal_match'):
        reasons.append(f"subtotal_not_exact:diff={diag.get('diff_to_subtotal')}")

    if not diag.get('exact_total_match'):
        reasons.append(f"total_not_exact:diff={diag.get('diff_to_total')}")

    if diag.get('subtotal_amount') is None:
        reasons.append('subtotal_missing')

    if diag.get('total_amount') is None:
        reasons.append('total_missing')

    if len(article_rows) <= 0:
        reasons.append('no_article_rows')

    reasons.extend(_article_blocker_reasons(article_rows))
    reasons.extend(_unused_fragment_reasons(unused_text_fragments))

    if unused_unit_fragments:
        reasons.append(f'unused_unit_fragments_present:{len(unused_unit_fragments)}')

    ready = len(reasons) == 0

    return {
        'mode': 'diagnose_only',
        'version': 'PLUS-01K',
        'ready_for_activation': ready,
        'readiness_reasons': reasons,
        'financial': {
            'article_total': diag.get('article_total'),
            'non_article_financial_total': diag.get('non_article_financial_total'),
            'pre_discount_total': diag.get('pre_discount_total'),
            'subtotal_amount': diag.get('subtotal_amount'),
            'diff_to_subtotal': diag.get('diff_to_subtotal'),
            'exact_subtotal_match': diag.get('exact_subtotal_match'),
            'discount_total': diag.get('discount_total'),
            'net_total': diag.get('net_total'),
            'total_amount': diag.get('total_amount'),
            'diff_to_total': diag.get('diff_to_total'),
            'exact_total_match': diag.get('exact_total_match'),
            'total_discount_control': diag.get('total_discount_control'),
        },
        'counts': {
            'article_rows': len(article_rows),
            'bbox_non_article_financial_rows': len(diag.get('bbox_non_article_financial_rows') or []),
            'extra_runtime_non_article_financial_rows': len(diag.get('extra_runtime_non_article_financial_rows') or []),
            'used_discount_rows': len([row for row in diag.get('discount_rows') or [] if row.get('used_in_total')]),
            'unused_text_fragments': len(unused_text_fragments),
            'unused_unit_fragments': len(unused_unit_fragments),
        },
        'article_rows': article_rows,
        'bbox_non_article_financial_rows': diag.get('bbox_non_article_financial_rows') or [],
        'extra_runtime_non_article_financial_rows': diag.get('extra_runtime_non_article_financial_rows') or [],
        'discount_rows': diag.get('discount_rows') or [],
        'unused_text_fragments': unused_text_fragments,
        'unused_unit_fragments': unused_unit_fragments,
        'chosen_total_candidate': diag.get('chosen_total_candidate'),
        'total_candidates': diag.get('total_candidates') or [],
    }


__all__ = ['diagnose_plus_bbox_activation_readiness']
