from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

_AMOUNT_TOKEN_RE = re.compile(r'[€£CE]?-?\d{1,6}(?:[\.,]\d{2})(?:\s*EUR)?', re.IGNORECASE)
_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
_PLUS_STORE_TOKENS = ('plus',)
_PLUSPUNTEN_TOKENS = ('pluspunten', 'piuspunten')
_SUBTOTAL_TOKENS = ('subtotaal',)
_TOTAL_TOKENS = ('totaal',)
_DISCOUNT_CONTEXT_TOKENS = ('plus geeft', 'voordeel', 'korting')
_CORRECTION_TOKENS = ('zegel', 'actie', 'pluspunten', 'piuspunten')
_QUANTITY_X_RE = re.compile(r'(?<![A-Za-z0-9])(?P<qty>\d{1,4}(?:[\.,]\d+)?)\s*[xX]\b')


def _money(value: Any) -> Decimal:
    if value is None or value == '':
        return Decimal('0.00')
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _norm(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _norm_key(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()


def _parse_amount_token(token: str) -> Decimal | None:
    raw = _norm(token).upper().replace('EUR', '').replace('€', '').replace('£', '').strip()
    sign = Decimal('-1') if raw.startswith('C-') or raw.startswith('E-') or raw.startswith('-') else Decimal('1')
    raw = raw.replace('C-', '').replace('E-', '').replace('C', '').replace('E', '').replace('-', '').replace(',', '.')
    try:
        return (Decimal(raw) * sign).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _parse_quantity_token(raw: Any) -> Decimal | None:
    cleaned = _norm(raw).replace(',', '.')
    cleaned = re.sub(r'[^0-9\-.]', '', cleaned)
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except Exception:
        return None
    if value <= 0:
        return None
    return value.quantize(Decimal('0.001')).normalize()


def _quantity_from_line(line: str) -> Decimal | None:
    normalized = _norm(line)
    if not normalized:
        return None
    match = _QUANTITY_X_RE.search(normalized)
    if not match:
        return None
    return _parse_quantity_token(match.group('qty'))


def _quantity_for_pluspunten_line(line: str) -> Decimal | None:
    normalized = _norm(line)
    lowered = normalized.lower()
    token_positions = [
        pos for token in _PLUSPUNTEN_TOKENS
        for pos in [lowered.find(token)]
        if pos >= 0
    ]
    if not token_positions:
        return None
    token_pos = min(token_positions)
    matches = list(_QUANTITY_X_RE.finditer(normalized))
    before_token = [match for match in matches if match.start() < token_pos]
    if before_token:
        return _parse_quantity_token(before_token[-1].group('qty'))
    if matches:
        return _parse_quantity_token(matches[-1].group('qty'))
    return None


def _pluspunten_norm_label(line: str) -> str:
    return 'PLUSPunten DIGITAAL' if 'digitaal' in _norm(line).lower() else 'PLUSPunten'


def _synthetic_pluspunten_raw_line(label: str, quantity: Decimal, amount: Decimal) -> str:
    quantity_text = str(quantity.normalize()).replace('.', ',')
    amount_text = str(amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)).replace('.', ',')
    return f"{quantity_text}X {label} {amount_text}"


def _float_decimal(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _amounts_from_line(line: str) -> list[Decimal]:
    values: list[Decimal] = []
    for token in _AMOUNT_TOKEN_RE.findall(line or ''):
        value = _parse_amount_token(token)
        if value is not None:
            values.append(value)
    return values


def _looks_like_plus_image_context(text_lines: list[str], store_name: str | None, filename: str | None) -> bool:
    suffix = Path(filename or '').suffix.lower()
    if suffix not in _IMAGE_EXTENSIONS:
        return False
    haystack = ' '.join([str(store_name or ''), *(str(line or '') for line in text_lines[:20])]).lower()
    return any(token in haystack for token in _PLUS_STORE_TOKENS)


def _is_correction_window_line(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in _CORRECTION_TOKENS)


def _classify_receipt_level_correction(line: str) -> Decimal | None:
    lowered = line.lower()
    if not _is_correction_window_line(line):
        return None
    amounts = _amounts_from_line(line)
    if not amounts:
        return None
    amount = amounts[-1]
    # PLUSPunten wins over ZEGEL: the line can contain both words, but points are a positive credit.
    if any(token in lowered for token in _PLUSPUNTEN_TOKENS):
        return abs(amount)
    if 'zegel' in lowered or 'actie' in lowered:
        return -abs(amount)
    return amount


def _subtotal_index(text_lines: list[str]) -> int | None:
    for index, line in enumerate(text_lines):
        lowered = str(line or '').lower()
        if any(token in lowered for token in _SUBTOTAL_TOKENS):
            return index
    return None


def _total_index_after(text_lines: list[str], subtotal_index: int) -> int | None:
    for index in range(subtotal_index + 1, len(text_lines)):
        lowered = str(text_lines[index] or '').lower()
        if any(token in lowered for token in _TOTAL_TOKENS):
            return index
    return None


def _subtotal_total_window(text_lines: list[str]) -> list[str]:
    subtotal_index = _subtotal_index(text_lines)
    if subtotal_index is None:
        return []
    total_index = _total_index_after(text_lines, subtotal_index)
    if total_index is None or total_index <= subtotal_index:
        return []
    return text_lines[subtotal_index + 1:total_index]


def _explicit_subtotal_total_amounts(text_lines: list[str]) -> tuple[Decimal | None, Decimal | None]:
    subtotal_index = _subtotal_index(text_lines)
    if subtotal_index is None:
        return None, None
    subtotal_amounts = _amounts_from_line(str(text_lines[subtotal_index] or ''))
    subtotal_amount = subtotal_amounts[-1] if subtotal_amounts else None
    total_amount = None
    total_index = _total_index_after(text_lines, subtotal_index)
    if total_index is not None:
        for line in text_lines[total_index: min(len(text_lines), total_index + 3)]:
            amounts = _amounts_from_line(str(line or ''))
            if amounts:
                total_amount = amounts[-1]
                break
    return subtotal_amount, total_amount


def _label_without_amount(line: str) -> str:
    label = _AMOUNT_TOKEN_RE.sub('', str(line or '')).strip()
    label = re.sub(r'\b\d+(?:[\.,]\d+)?\s*[xX]\b', '', label)
    return _norm(label).strip(' .:-')


def _best_line_match(lines: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    label_key = _norm_key(label)
    if not label_key:
        return None
    best: tuple[int, dict[str, Any]] | None = None
    label_tokens = set(label_key.split())
    for line in lines:
        candidate = str(line.get('raw_label') or line.get('normalized_label') or '')
        candidate_key = _norm_key(candidate)
        if not candidate_key:
            continue
        candidate_tokens = set(candidate_key.split())
        overlap = len(label_tokens & candidate_tokens)
        if not overlap:
            continue
        score = overlap * 10
        if label_key in candidate_key or candidate_key in label_key:
            score += 100
        if best is None or score > best[0]:
            best = (score, line)
    return best[1] if best else None


def _apply_plus_line_discounts(text_lines: list[str], lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjusted = [dict(line) for line in lines]
    previous_article_line: str | None = None
    for raw_line in text_lines:
        line = _norm(raw_line)
        lowered = line.lower()
        amounts = _amounts_from_line(line)
        if any(token in lowered for token in _DISCOUNT_CONTEXT_TOKENS) and amounts:
            discount_amount = amounts[-1]
            if discount_amount >= 0 or previous_article_line is None:
                continue
            label = _label_without_amount(previous_article_line)
            target = _best_line_match(adjusted, label)
            if target is None:
                continue
            current_discount = _money(target.get('discount_amount'))
            if current_discount == Decimal('0.00'):
                target['discount_amount'] = float(discount_amount)
            continue
        if amounts and not any(token in lowered for token in _SUBTOTAL_TOKENS + _TOTAL_TOKENS + _CORRECTION_TOKENS + _DISCOUNT_CONTEXT_TOKENS):
            previous_article_line = line
    return adjusted



_PLUS_CORRECTION_MATCH_STOPWORDS = {
    'x', 'ox', '1x', '2x', '3x', 'zegel', 'zegels', 'actie', 'pluspunten', 'piuspunten',
    'digitaal', 'the', 'voice', 'meer', 'voordeel', 'geeft', 'plus', 'subtotaal', 'totaal',
}

def _match_tokens(value: Any) -> set[str]:
    raw = _norm_key(value)
    tokens: set[str] = set()
    for token in raw.split():
        if len(token) < 3:
            continue
        if token in _PLUS_CORRECTION_MATCH_STOPWORDS:
            continue
        if token.isdigit():
            continue
        tokens.add(token)
    return tokens


def _common_prefix_len(left: str, right: str) -> int:
    count = 0
    for a, b in zip(left, right):
        if a != b:
            break
        count += 1
    return count


def _prefix_token_overlap(left: set[str], right: set[str]) -> int:
    score = 0
    for a in left:
        for b in right:
            # OCR often truncates product names, e.g. WERELDGERECH -> WERELDGER.
            if a == b or a.startswith(b[:5]) or b.startswith(a[:5]):
                score += 2
                continue

            # R9-38C3b:
            # Generic PLUS action-linking fallback. Some PLUS subtotal action
            # lines contain a brand/campaign token while the article line has a
            # related compound product token. We allow a weak shared-prefix match
            # only for longer tokens and only inside the PLUS profile. This keeps
            # the behavior generic and avoids receipt/article-name hardcoding.
            common_prefix = _common_prefix_len(a, b)
            if len(a) >= 7 and len(b) >= 7 and common_prefix >= 3:
                score += 1
    return score


def _line_source_index(line: dict[str, Any]) -> int:
    try:
        return int(line.get('source_index') or 0)
    except Exception:
        return 0


def _article_candidates_before_subtotal(text_lines: list[str], lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    subtotal = _subtotal_index(text_lines)
    candidates: list[dict[str, Any]] = []
    for line in lines:
        label = _norm(line.get('raw_label') or line.get('normalized_label'))
        if not label:
            continue
        label_key = _norm_key(label)
        if any(token in label_key for token in _CORRECTION_TOKENS):
            continue
        source_index = _line_source_index(line)
        if subtotal is not None and source_index > 0 and source_index >= subtotal:
            continue
        candidates.append(line)
    return candidates


def _negative_subtotal_corrections(text_lines: list[str]) -> list[dict[str, Any]]:
    window = _subtotal_total_window(text_lines)
    subtotal = _subtotal_index(text_lines) or 0
    corrections: list[dict[str, Any]] = []

    for offset, raw_line in enumerate(window, start=subtotal + 1):
        line = _norm(raw_line)
        lowered = line.lower()

        # PLUSPunten is a visible norm row, not an article discount.
        if any(token in lowered for token in _PLUSPUNTEN_TOKENS):
            continue

        amount = _classify_receipt_level_correction(line)
        if amount is None or amount >= 0:
            continue

        corrections.append({
            'source_index': offset,
            'raw_line': line,
            'amount': amount,
            'quantity': _quantity_from_line(line),
            'tokens': _match_tokens(line),
        })

    return corrections


def _score_plus_correction_target(correction: dict[str, Any], line: dict[str, Any], used_ids: set[Any]) -> int:
    line_id = line.get('id') or id(line)
    if line_id in used_ids:
        return -999

    amount = abs(_money(correction.get('amount')))
    line_total = abs(_money(line.get('line_total')))
    line_quantity = _parse_quantity_token(line.get('quantity'))
    correction_quantity = correction.get('quantity')
    line_tokens = _match_tokens(line.get('raw_label') or line.get('normalized_label'))
    correction_tokens = correction.get('tokens') or set()

    score = 0

    token_overlap = _prefix_token_overlap(correction_tokens, line_tokens)
    score += token_overlap * 70

    if amount != Decimal('0.00') and abs(amount - line_total) <= Decimal('0.02'):
        score += 90

    if (
        correction_quantity is not None
        and line_quantity is not None
        and abs(correction_quantity - line_quantity) <= Decimal('0.001')
    ):
        score += 25

    # Prefer article lines without an existing discount, but still allow adding
    # if the article already has a PLUS line-level discount.
    existing_discount = _money(line.get('discount_amount'))
    if existing_discount == Decimal('0.00'):
        score += 10

    return score


def _attach_plus_subtotal_corrections_to_article_lines(
    *,
    text_lines: list[str],
    lines: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], Decimal, list[dict[str, Any]]]:
    """Attach negative PLUS subtotal correction rows to article lines.

    Generic PLUS profile behavior:
    - below-subtotal PLUSPunten stays a visible norm row elsewhere;
    - negative ZEGEL/ACTIE rows are article discounts when confidently linkable;
    - matching uses token/fuzzy prefix overlap, amount match, quantity signal and
      article-block position;
    - no receipt-id, filename or article-name hardcoding.
    """
    corrections = _negative_subtotal_corrections(text_lines)
    if not corrections:
        return lines, Decimal('0.00'), []

    adjusted = [dict(line) for line in lines]
    candidates = _article_candidates_before_subtotal(text_lines, adjusted)
    if not candidates:
        return adjusted, Decimal('0.00'), []

    used_ids: set[Any] = set()
    linked_total = Decimal('0.00')
    links: list[dict[str, Any]] = []

    for correction in corrections:
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for candidate in candidates:
            score = _score_plus_correction_target(correction, candidate, used_ids)
            source_distance = abs(_line_source_index(candidate) - int(correction.get('source_index') or 0))
            scored.append((score, -source_distance, candidate))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not scored:
            continue

        best_score, _distance_score, target = scored[0]

        # Guardrail: either token/fuzzy match, exact amount match or quantity signal must support the link.
        correction_amount_abs = abs(_money(correction.get('amount')))
        target_line_total_abs = abs(_money(target.get('line_total')))
        has_amount_match = abs(correction_amount_abs - target_line_total_abs) <= Decimal('0.02')
        has_token_match = _prefix_token_overlap(correction.get('tokens') or set(), _match_tokens(target.get('raw_label') or target.get('normalized_label'))) > 0
        has_quantity_match = (
            correction.get('quantity') is not None
            and _parse_quantity_token(target.get('quantity')) is not None
            and abs(correction.get('quantity') - _parse_quantity_token(target.get('quantity'))) <= Decimal('0.001')
        )

        if best_score < 60 and not (has_amount_match or has_token_match or has_quantity_match):
            continue

        current_discount = _money(target.get('discount_amount'))
        correction_amount = _money(correction.get('amount'))
        target['discount_amount'] = float((current_discount + correction_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

        target_id = target.get('id') or id(target)
        used_ids.add(target_id)
        linked_total += correction_amount

        trace = dict(target.get('producer_trace') or {})
        plus_links = list(trace.get('plus_subtotal_correction_links') or [])
        plus_links.append({
            'source': 'R9-38C3_PLUS_subtotal_correction_link',
            'raw_line': correction.get('raw_line'),
            'amount': float(correction_amount),
            'score': int(best_score),
            'target_label': target.get('raw_label') or target.get('normalized_label'),
            'match': {
                'amount_match': bool(has_amount_match),
                'token_match': bool(has_token_match),
                'quantity_match': bool(has_quantity_match),
            },
        })
        trace['plus_subtotal_correction_links'] = plus_links
        target['producer_trace'] = trace

        links.append({
            'raw_line': correction.get('raw_line'),
            'amount': float(correction_amount),
            'target_label': target.get('raw_label') or target.get('normalized_label'),
            'score': int(best_score),
        })

    return adjusted, linked_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), links



def _enrich_plus_quantities_from_text_lines(text_lines: list[str], lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Infer visible `nX` quantities for PLUS photo rows without changing totals.

    This is deliberately conservative: it only fills an empty quantity from the
    exact source OCR line (or its producer trace), and it does not recalculate
    line totals. Existing parser quantities/unit prices win.
    """
    enriched: list[dict[str, Any]] = []
    for line in lines:
        adjusted = dict(line)
        if adjusted.get('quantity') not in (None, ''):
            enriched.append(adjusted)
            continue
        source_text = ''
        source_index = adjusted.get('source_index')
        if isinstance(source_index, int) and 0 <= source_index < len(text_lines):
            source_text = _norm(text_lines[source_index])
        if not source_text:
            producer_trace = adjusted.get('producer_trace') or {}
            if isinstance(producer_trace, dict):
                source_text = _norm(producer_trace.get('raw_line') or producer_trace.get('normalized_line'))
        if not source_text:
            source_text = _norm(adjusted.get('raw_label') or adjusted.get('normalized_label'))
        quantity = _quantity_from_line(source_text)
        if quantity is None:
            enriched.append(adjusted)
            continue
        adjusted['quantity'] = _float_decimal(quantity)
        if adjusted.get('unit_price') in (None, ''):
            line_total = _money(adjusted.get('line_total'))
            if line_total != Decimal('0.00'):
                adjusted['unit_price'] = _float_decimal((line_total / quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        trace = dict(adjusted.get('producer_trace') or {})
        trace['quantity_enrichment'] = {
            'applied': True,
            'source': 'R9-38B17_PLUS_visible_nX_quantity',
            'source_text': source_text,
            'quantity': float(quantity),
            'totals_unchanged': True,
        }
        adjusted['producer_trace'] = trace
        enriched.append(adjusted)
    return enriched


def _receipt_level_correction_total(text_lines: list[str]) -> Decimal | None:
    window = _subtotal_total_window(text_lines)
    if not window:
        return None
    total = Decimal('0.00')
    found = False
    for line in window:
        amount = _classify_receipt_level_correction(line)
        if amount is None:
            continue
        found = True
        total += amount
    return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if found else None


def _build_correction_norm_line(*, label: str, amount: Decimal, source_index: int, raw_line: str, filename: str | None) -> dict[str, Any]:
    cleaned_label = re.sub(r'^[^A-Za-z0-9]+', '', label).strip(' .:-') or 'PLUS correctieregel'
    quantity = _quantity_from_line(raw_line)
    unit_price = amount
    if quantity is not None and quantity > 0:
        unit_price = (amount / quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {
        'raw_label': cleaned_label,
        'normalized_label': cleaned_label,
        'quantity': _float_decimal(quantity),
        'unit': None,
        'unit_price': float(unit_price),
        'line_total': float(amount),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': 0.85,
        'source_index': source_index,
        'producer_trace': {
            'filename': filename,
            'store_name': 'PLUS',
            'function_name': '_extract_savings_action_lines',
            'append_branch': 'savings_action_line',
            'parser_path': 'r9_38b16.plus_correction_norm_line',
            'source_index': source_index,
            'raw_line': raw_line,
            'normalized_line': raw_line,
            'label': cleaned_label,
            'raw_label': cleaned_label,
            'amount': float(amount),
            'quantity': float(quantity) if quantity is not None else None,
            'classification': 'validated_savings_action_line',
            'classification_allows_append': True,
            'append_allowed': True,
            'caller_line_hint': 'R9-38B16 PLUS baseline correction norm line',
            'validated_savings_action_path': True,
        },
    }


def _correction_norm_line_candidate(
    text_lines: list[str],
    lines: list[dict[str, Any]],
    receipt_correction_total: Decimal | None,
    filename: str | None,
) -> tuple[dict[str, Any], Decimal] | None:
    if receipt_correction_total is None or receipt_correction_total == Decimal('0.00'):
        return None

    subtotal_amount, total_amount = _explicit_subtotal_total_amounts(text_lines)
    if subtotal_amount is None or total_amount is None:
        return None

    window = _subtotal_total_window(text_lines)
    if not window:
        return None

    article_sum = sum(
        (_money(line.get('line_total')) + _money(line.get('discount_amount')) for line in lines),
        Decimal('0.00')
    ).quantize(Decimal('0.01'))

    if abs(article_sum - subtotal_amount) > Decimal('0.02'):
        return None
    if abs((article_sum + receipt_correction_total) - total_amount) > Decimal('0.02'):
        return None

    correction_tokens = _CORRECTION_TOKENS
    if any(any(token in _norm_key(line.get('raw_label') or line.get('normalized_label')) for token in correction_tokens) for line in lines):
        return None

    subtotal_index = _subtotal_index(text_lines) or 0
    pluspoints_line: tuple[int, str, str, Decimal, Decimal] | None = None
    explicit_zegel_line: tuple[int, str, Decimal] | None = None
    correction_lines: list[tuple[int, str, Decimal]] = []

    for offset, raw_line in enumerate(window, start=subtotal_index + 1):
        line = _norm(raw_line)
        lowered = line.lower()
        correction_amount = _classify_receipt_level_correction(line)
        if correction_amount is None:
            continue

        correction_lines.append((offset, line, correction_amount))

        # Generiek PLUS: PLUSPunten/PiUSPunten wint altijd als zichtbare normregel.
        if any(token in lowered for token in _PLUSPUNTEN_TOKENS):
            quantity = _quantity_for_pluspunten_line(line)
            amounts = _amounts_from_line(line)
            if quantity is not None and amounts:
                label = _pluspunten_norm_label(line)
                amount = abs(amounts[-1])
                pluspoints_line = (offset, line, label, quantity, amount)
                continue

        # Fallback alleen als er géén PLUSPunten-regel is.
        if 'zegel' in lowered and _quantity_from_line(line) is not None:
            amounts = _amounts_from_line(line)
            if amounts:
                explicit_zegel_line = (offset, line, abs(amounts[-1]))

    if pluspoints_line is not None:
        source_index, raw_line, label, quantity, amount = pluspoints_line
        return _build_correction_norm_line(
            label=label,
            amount=amount,
            source_index=source_index,
            raw_line=_synthetic_pluspunten_raw_line(label, quantity, amount),
            filename=filename,
        ), amount

    if explicit_zegel_line is not None:
        source_index, raw_line, amount = explicit_zegel_line
        return _build_correction_norm_line(
            label=_label_without_amount(raw_line),
            amount=amount,
            source_index=source_index,
            raw_line=raw_line,
            filename=filename,
        ), amount

    if not correction_lines:
        return None

    source_index, raw_line, correction_amount = correction_lines[-1]
    aggregate_label = _label_without_amount(raw_line) or 'PLUS correctieregel'
    return _build_correction_norm_line(
        label=aggregate_label,
        amount=correction_amount,
        source_index=source_index,
        raw_line=raw_line,
        filename=filename,
    ), correction_amount

def apply_plus_runtime_corrections(
    *,
    text_lines: list[str],
    lines: list[dict[str, Any]],
    discount_total: Decimal | None,
    store_name: str | None,
    filename: str | None,
) -> tuple[list[dict[str, Any]], Decimal | None, dict[str, Any] | None]:
    if not _looks_like_plus_image_context(text_lines, store_name, filename):
        return lines, discount_total, None

    # 1. Start with existing PLUS line-level discounts and visible nX quantities.
    corrected_lines = _apply_plus_line_discounts(text_lines, lines)
    corrected_lines = _enrich_plus_quantities_from_text_lines(text_lines, corrected_lines)

    # 2. Determine the full receipt-level subtotal/total correction window.
    receipt_correction_total = _receipt_level_correction_total(text_lines)

    # 3. Determine the visible PLUSPunten/PiUSPunten norm line BEFORE attaching
    #    negative subtotal corrections. This preserves the baseline line_count.
    norm_line_candidate = _correction_norm_line_candidate(
        text_lines,
        corrected_lines,
        receipt_correction_total,
        filename,
    )

    norm_line = None
    norm_amount = Decimal('0.00')
    if norm_line_candidate is not None:
        norm_line, norm_amount = norm_line_candidate

    # 4. Now attach only reliably linkable negative subtotal corrections to
    #    article rows. These amounts are removed from the remaining receipt-level
    #    correction to avoid double counting.
    linked_subtotal_correction_total = Decimal('0.00')
    linked_subtotal_corrections: list[dict[str, Any]] = []
    if "_attach_plus_subtotal_corrections_to_article_lines" in globals():
        corrected_lines, linked_subtotal_correction_total, linked_subtotal_corrections = _attach_plus_subtotal_corrections_to_article_lines(
            text_lines=text_lines,
            lines=corrected_lines,
        )

    if norm_line is not None:
        corrected_lines = [*corrected_lines, norm_line]

    # 5. Prevent double counting:
    #    receipt_correction_total contains PLUSPunten and negative subtotal rows.
    #    The norm line is now a visible line, and linked negative corrections are
    #    now line-level discounts. Only the remainder stays in discount_total.
    remaining_receipt_correction = discount_total
    if receipt_correction_total is not None:
        remaining = (
            receipt_correction_total
            - norm_amount
            - linked_subtotal_correction_total
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        remaining_receipt_correction = remaining if remaining != Decimal('0.00') else None

    diagnostics = {
        'r9_38c3a_plus_subtotal_correction_recovery': {
            'applied': True,
            'norm_line_applied': norm_line is not None,
            'norm_line_amount': float(norm_amount),
            'linked_subtotal_correction_total': float(linked_subtotal_correction_total),
            'linked_subtotal_corrections': linked_subtotal_corrections,
            'receipt_level_correction_total_before_links': float(receipt_correction_total or Decimal('0.00')),
            'receipt_level_correction_total_after_links': float(remaining_receipt_correction or Decimal('0.00')),
            'double_counting_prevented': True,
            'quantity_enrichment_applied': any(
                bool((line.get('producer_trace') or {}).get('quantity_enrichment'))
                for line in corrected_lines
            ),
            'scope': 'PLUS profile image receipts only',
        }
    }

    return corrected_lines, remaining_receipt_correction, diagnostics

