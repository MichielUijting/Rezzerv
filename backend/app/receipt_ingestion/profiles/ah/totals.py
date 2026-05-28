"""Albert Heijn total extraction profile.

R9-36B mini frame: determine only the explicit AH receipt total from
raw/normalized source lines. No article parsing, no store-branch parsing,
no status decisions, and no line-sum fallback.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable

from .detect import looks_like_ah_context


AMOUNT_RE = re.compile(r'(?<!\d)(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))(?!\d)')
REJECT_TOKENS = (
    'subtotaal',
    'btw',
    'pin',
    'pinnen',
    'betaald',
    'bankpas',
    'maestro',
    'v pay',
    'v-pay',
    'voordeel',
    'bonus',
    'korting',
    'koopzegels',
)


@dataclass(frozen=True)
class AhTotalCandidate:
    anchor: str
    amount: Decimal
    line_index: int
    raw_line: str
    priority: int
    source: str = 'same_line'


@dataclass(frozen=True)
class AhTotalResult:
    amount: Decimal | None
    explicit_total_found: bool
    selected: dict | None
    candidates: list[dict]
    rejected: list[dict]


def _normalize(value: object) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _anchor_normalized(value: object) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip().upper()


def _parse_amount(value: str) -> Decimal | None:
    raw = str(value or '').strip().replace('€', '').replace('EUR', '').replace('eur', '')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    else:
        raw = raw.replace(',', '.')
    try:
        return Decimal(raw).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def _candidate_to_dict(candidate: AhTotalCandidate) -> dict:
    result = asdict(candidate)
    result['amount'] = str(candidate.amount)
    return result


def _contains_reject_token(line: str) -> str | None:
    lowered = line.lower()
    for token in REJECT_TOKENS:
        if token in lowered:
            return token
    return None


def _line_anchor(line_without_amount: str) -> str | None:
    normalized = _anchor_normalized(line_without_amount.strip(' .:-\t'))
    if normalized == 'TE BETALEN':
        return 'TE BETALEN'
    if normalized == 'TOTAAL':
        return 'TOTAAL'
    return None


def _inspect_line(raw_line: object, line_index: int) -> tuple[AhTotalCandidate | None, dict | None]:
    line = _normalize(raw_line)
    if not line:
        return None, {'line_index': line_index, 'raw_line': '', 'reason': 'empty_line'}

    reject_token = _contains_reject_token(line)
    if reject_token:
        return None, {
            'line_index': line_index,
            'raw_line': line,
            'reason': 'reject_token',
            'token': reject_token,
        }

    amount_matches = list(AMOUNT_RE.finditer(line))
    if not amount_matches:
        return None, {
            'line_index': line_index,
            'raw_line': line,
            'reason': 'no_amount',
        }
    if len(amount_matches) != 1:
        return None, {
            'line_index': line_index,
            'raw_line': line,
            'reason': 'multiple_amounts',
            'amounts': [match.group('amount') for match in amount_matches],
        }

    amount_match = amount_matches[0]
    amount = _parse_amount(amount_match.group('amount'))
    if amount is None:
        return None, {
            'line_index': line_index,
            'raw_line': line,
            'reason': 'invalid_amount',
            'amount': amount_match.group('amount'),
        }

    line_without_amount = f'{line[:amount_match.start()]} {line[amount_match.end():]}'
    anchor = _line_anchor(line_without_amount)
    if anchor is None:
        return None, {
            'line_index': line_index,
            'raw_line': line,
            'reason': 'no_exact_anchor_same_line',
        }

    return AhTotalCandidate(
        anchor=anchor,
        amount=amount,
        line_index=line_index,
        raw_line=line,
        priority=0 if anchor == 'TE BETALEN' else 1,
    ), None


def extract_ah_total_amount(
    text_lines: Iterable[object] | None,
    filename: str | None = None,
    *,
    store_name: str | None = None,
) -> AhTotalResult:
    """Extract explicit AH total amount from same-line anchors only.

    Valid examples:
    - "TE BETALEN 5,40"
    - "TOTAAL 8,28"

    Invalid by design:
    - line N: "TE BETALEN", line N+1: "5,40"
    - article line sums or inferred totals
    """
    if not looks_like_ah_context(text_lines, filename, store_name=store_name):
        return AhTotalResult(
            amount=None,
            explicit_total_found=False,
            selected=None,
            candidates=[],
            rejected=[{'reason': 'not_ah_context'}],
        )

    candidates: list[AhTotalCandidate] = []
    rejected: list[dict] = []
    for line_index, raw_line in enumerate(text_lines or []):
        candidate, rejection = _inspect_line(raw_line, line_index)
        if candidate is not None:
            candidates.append(candidate)
        elif rejection is not None and rejection.get('reason') not in {'no_amount', 'no_exact_anchor_same_line'}:
            rejected.append(rejection)

    selected_candidate = None
    if candidates:
        selected_candidate = sorted(candidates, key=lambda item: (item.priority, item.line_index))[0]

    selected = _candidate_to_dict(selected_candidate) if selected_candidate else None
    return AhTotalResult(
        amount=selected_candidate.amount if selected_candidate else None,
        explicit_total_found=selected_candidate is not None,
        selected=selected,
        candidates=[_candidate_to_dict(candidate) for candidate in candidates],
        rejected=rejected,
    )
