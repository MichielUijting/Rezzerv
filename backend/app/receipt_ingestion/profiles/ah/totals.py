"""Albert Heijn total extraction.

AH-specific total semantics belong in this profile module. Generic parsing may
call this profile, but must not own AH rules.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Callable

from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal
from app.receipt_ingestion.fingerprints import _is_plausible_total_amount

AmountParser = Callable[[str], Decimal | None]
AmountPlausibility = Callable[[Decimal], bool]


@dataclass(frozen=True)
class AhTotalCandidate:
    line_index: int
    raw_line: str
    normalized_anchor_after_amount_removal: str
    amount_count: int
    amounts: list[str]
    accepted: bool
    reason: str
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AhTotalExtractionResult:
    amount: Decimal | None
    explicit_total_found: bool
    diagnostics: dict[str, Any] = field(default_factory=dict)


def looks_like_ah_context(text_lines: list[str], filename: str, store_name: str | None = None) -> bool:
    haystack = ' '.join(str(line or '') for line in text_lines[:20]).lower()
    lower_filename = str(filename or '').lower()
    normalized_store = str(store_name or '').strip().lower()
    return (
        normalized_store in {'albert heijn', 'ah'}
        or 'ah ' in lower_filename
        or 'ah_' in lower_filename
        or 'albert heijn' in haystack
        or 'ah to go' in haystack
        or re.search(r'\bah\b', haystack) is not None
    )


def _normalize_total_anchor(value: str | None) -> str:
    normalized = str(value or '').upper()
    normalized = re.sub(r'[^A-Z\s]+', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def _line_without_amounts(value: str | None) -> str:
    cleaned = re.sub(r'(?<!\d)-?\d{1,6}(?:[\.,]\d{2})(?!\d)', ' ', str(value or ''))
    cleaned = re.sub(r'\b(?:EUR|EURO)\b|€', ' ', cleaned, flags=re.IGNORECASE)
    return cleaned


def _amounts_from_text(
    value: str | None,
    *,
    parse_amount: AmountParser = _parse_decimal,
    is_plausible_amount: AmountPlausibility = _is_plausible_total_amount,
) -> list[Decimal]:
    amounts: list[Decimal] = []
    for match in re.finditer(r'(?<!\d)(-?\d{1,6}(?:[\.,]\d{2}))(?!\d)', str(value or '')):
        parsed = parse_amount(match.group(1))
        if parsed is not None and is_plausible_amount(parsed):
            amounts.append(parsed)
    return amounts


def _priority(anchor: str) -> int:
    return 200 if anchor == 'TE BETALEN' else 100


def extract_ah_total_amount(
    text_lines: list[str],
    filename: str,
    *,
    store_name: str | None = None,
    parse_amount: AmountParser = _parse_decimal,
    is_plausible_amount: AmountPlausibility = _is_plausible_total_amount,
) -> AhTotalExtractionResult:
    candidates: list[AhTotalCandidate] = []

    if not looks_like_ah_context(text_lines, filename, store_name):
        return AhTotalExtractionResult(
            amount=None,
            explicit_total_found=False,
            diagnostics={
                'profile': 'ah',
                'extractor': 'profiles.ah.totals.extract_ah_total_amount',
                'applicable': False,
                'reason': 'no_ah_context',
                'accepted_total_candidate': None,
                'rejected_total_candidates': [],
            },
        )

    for index, raw_line in enumerate(text_lines):
        line = str(raw_line or '').strip()
        if not line:
            continue
        same_line_amounts = _amounts_from_text(
            line,
            parse_amount=parse_amount,
            is_plausible_amount=is_plausible_amount,
        )
        if same_line_amounts:
            anchor_after_amount_removal = _normalize_total_anchor(_line_without_amounts(line))
            amount_strings = [str(item) for item in same_line_amounts]
            if len(same_line_amounts) != 1:
                candidates.append(AhTotalCandidate(index, line, anchor_after_amount_removal, len(same_line_amounts), amount_strings, False, 'multiple_amounts_rejected'))
                continue
            if anchor_after_amount_removal not in {'TOTAAL', 'TE BETALEN'}:
                candidates.append(AhTotalCandidate(index, line, anchor_after_amount_removal, 1, amount_strings, False, 'anchor_not_exact_after_amount_removal'))
                continue
            candidates.append(AhTotalCandidate(index, line, anchor_after_amount_removal, 1, amount_strings, True, 'accepted_same_line_exact_anchor', _priority(anchor_after_amount_removal)))
            continue

        anchor = _normalize_total_anchor(line)
        if anchor not in {'TOTAAL', 'TE BETALEN'}:
            continue
        if index + 1 >= len(text_lines):
            candidates.append(AhTotalCandidate(index, line, anchor, 0, [], False, 'exact_anchor_without_next_line'))
            continue
        next_line = str(text_lines[index + 1] or '').strip()
        next_amounts = _amounts_from_text(
            next_line,
            parse_amount=parse_amount,
            is_plausible_amount=is_plausible_amount,
        )
        next_residue = _normalize_total_anchor(_line_without_amounts(next_line))
        amount_strings = [str(item) for item in next_amounts]
        if len(next_amounts) != 1:
            candidates.append(AhTotalCandidate(index, f'{line} -> {next_line}', anchor, len(next_amounts), amount_strings, False, 'next_line_amount_count_not_one'))
            continue
        if next_residue:
            candidates.append(AhTotalCandidate(index, f'{line} -> {next_line}', anchor, 1, amount_strings, False, 'next_line_contains_text_residue'))
            continue
        candidates.append(AhTotalCandidate(index, f'{line} -> {next_line}', anchor, 1, amount_strings, True, 'accepted_next_line_exact_anchor', _priority(anchor)))

    accepted = [candidate for candidate in candidates if candidate.accepted]
    accepted.sort(key=lambda item: (-item.priority, item.line_index))
    selected = accepted[0] if accepted else None
    selected_amount = Decimal(selected.amounts[0]) if selected else None
    return AhTotalExtractionResult(
        amount=selected_amount,
        explicit_total_found=selected is not None,
        diagnostics={
            'profile': 'ah',
            'extractor': 'profiles.ah.totals.extract_ah_total_amount',
            'applicable': True,
            'selected_anchor': selected.normalized_anchor_after_amount_removal if selected else None,
            'selected_amount': str(selected_amount) if selected_amount is not None else None,
            'accepted_total_candidate': selected.to_dict() if selected else None,
            'rejected_total_candidates': [candidate.to_dict() for candidate in candidates if not candidate.accepted],
            'candidate_count': len(candidates),
            'accepted_candidate_count': len(accepted),
            'ssot_guardrails': {
                'status_determination': 'not_performed_by_profile',
                'total_from_article_line_sum': False,
                'database_mutation': False,
            },
        },
    )
