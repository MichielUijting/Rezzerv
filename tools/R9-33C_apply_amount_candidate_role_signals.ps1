$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-33C apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path
import re

path = Path('backend/app/testing_receipt_line_diagnosis_routes.py')
text = path.read_text(encoding='utf-8')

start_marker = 'def _build_amount_line_candidates(engine_name: str, raw_lines: list[str] | None) -> list[dict[str, Any]]:'
end_marker = '\n\ndef _line_summary'
if start_marker not in text:
    raise SystemExit('R9-33C failed: candidate function anchor not found')
start = text.index(start_marker)
end = text.index(end_marker, start)

replacement = r'''def _canonical_amount(value: str | None) -> str:
    token = _normalize_ocr_amount_token(value)
    token = token.replace(',', '.')
    return token


def _canonical_candidate_line(value: str | None) -> str:
    text_value = re.sub(r'\s+', ' ', str(value or '').strip().lower())
    text_value = text_value.replace('€', '').replace('£', '').replace('$', '')
    return text_value


def _candidate_role_signals(normalized_line: str, amounts: list[str]) -> dict[str, Any]:
    lower = normalized_line.lower()
    role_signals: list[str] = []
    false_positive_signals: list[str] = []

    has_amount = bool(amounts)
    has_negative_amount = any(str(amount).strip().startswith('-') for amount in amounts)
    amount_count = len(amounts)
    word_count = len(re.findall(r'[A-Za-zÀ-ÿ]{2,}', normalized_line))
    digit_count = len(re.findall(r'\d', normalized_line))

    if re.search(r'\b(totaal|sub\s*totaal|subtotaal)\b', lower):
        role_signals.append('total_or_subtotal')
    if re.search(r'\b(pin|pinnen|bankpas|vpay|v-pay|maestro|visa|betaling|betaald|contant|wisselgeld)\b', lower):
        role_signals.append('payment')
    if re.search(r'\b(btw|bedr\.?\s*excl|incl\.?)\b', lower) or re.search(r'\d+[\.,]\d{2}%|\b\d+%\b', lower):
        role_signals.append('vat_or_tax')
    if re.search(r'\b(korting|bonus|actie|voordeel|gratis)\b', lower) or has_negative_amount:
        role_signals.append('discount_or_promotion')
    if re.search(r'\b(zegel|zegels|koopzegel|koopzegels|spaarzegel|spaarzegels|punten|pluspunten|airmiles)\b', lower):
        role_signals.append('savings_or_loyalty')

    if re.search(r'\b(openingstijden|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag|uur)\b', lower):
        false_positive_signals.append('opening_hours_or_time')
    if re.search(r'\b\d{1,2}[:.]\d{2}\b', lower) and re.search(r'\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b', lower):
        false_positive_signals.append('date_time_line')
    elif re.search(r'\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b', lower):
        false_positive_signals.append('date_line')
    elif re.search(r'\b\d{1,2}[:.]\d{2}\b', lower) and word_count <= 3:
        false_positive_signals.append('time_line')
    if re.search(r'\b(transactie|terminal|merchant|kaart|kaartnr|kaartserienummer|autorisatiecode|poi|pos|store|bonnr|periode)\b', lower) and not re.search(r'\b(totaal|pin|pinnen|bankpas|vpay|betaling|betaald)\b', lower):
        false_positive_signals.append('transaction_metadata')

    non_article_roles = {'total_or_subtotal', 'payment', 'vat_or_tax', 'discount_or_promotion', 'savings_or_loyalty'}
    has_non_article_role = any(role in non_article_roles for role in role_signals)
    has_false_positive_signal = bool(false_positive_signals)
    likely_article_candidate = bool(has_amount and word_count >= 1 and not has_non_article_role and not has_false_positive_signal)

    return {
        'role_signals': sorted(set(role_signals)),
        'false_positive_signals': sorted(set(false_positive_signals)),
        'likely_article_candidate': likely_article_candidate,
        'likely_non_article_candidate': has_non_article_role or has_false_positive_signal,
        'amount_count': amount_count,
        'has_negative_amount': has_negative_amount,
        'word_count': word_count,
        'digit_count': digit_count,
        'signal_scope': 'generic_store_independent_preclassification',
    }


def _build_amount_line_candidates(engine_name: str, raw_lines: list[str] | None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, raw_line in enumerate(raw_lines or []):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        if not normalized:
            continue
        amounts = _extract_ocr_amounts(normalized)
        compact_match = bool(COMPACT_AMOUNT_LINE_PATTERN.search(normalized))
        if not amounts and not compact_match:
            continue
        signals = _candidate_role_signals(normalized, amounts)
        candidates.append({
            'source_engine': engine_name,
            'source_line_index': index,
            'raw_line': raw_line,
            'normalized_line': normalized,
            'amounts_detected': amounts,
            'last_amount': amounts[-1] if amounts else None,
            'canonical_last_amount': _canonical_amount(amounts[-1]) if amounts else None,
            'candidate_type_unclassified': True,
            'classification_applied': False,
            'store_filtering_applied': False,
            'deduplication_applied': True,
            'reason': 'amount_pattern_detected_before_store_filtering',
            **signals,
        })
    return candidates


def _deduplicate_amount_line_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    preferred_engine_order = {'paddle': 0, 'tesseract': 1}

    for candidate in candidates:
        amounts_key = '|'.join(_canonical_amount(amount) for amount in candidate.get('amounts_detected') or [])
        key = (_canonical_candidate_line(candidate.get('normalized_line')), amounts_key)
        if key not in seen:
            candidate['dedupe_status'] = 'unique'
            candidate['duplicate_of'] = None
            seen[key] = candidate
            unique.append(candidate)
            continue

        existing = seen[key]
        candidate['dedupe_status'] = 'duplicate'
        candidate['duplicate_of'] = {
            'source_engine': existing.get('source_engine'),
            'source_line_index': existing.get('source_line_index'),
            'normalized_line': existing.get('normalized_line'),
        }
        duplicates.append(candidate)

        current_rank = preferred_engine_order.get(str(candidate.get('source_engine') or ''), 99)
        existing_rank = preferred_engine_order.get(str(existing.get('source_engine') or ''), 99)
        if current_rank < existing_rank:
            existing['dedupe_status'] = 'duplicate_replaced_by_preferred_engine'
            existing['duplicate_of'] = {
                'source_engine': candidate.get('source_engine'),
                'source_line_index': candidate.get('source_line_index'),
                'normalized_line': candidate.get('normalized_line'),
            }
            candidate['dedupe_status'] = 'unique'
            candidate['duplicate_of'] = None
            index = unique.index(existing)
            unique[index] = candidate
            seen[key] = candidate

    unique.sort(key=lambda item: (int(item.get('source_line_index') or 0), str(item.get('source_engine') or '')))
    return unique, duplicates


def _ocr_amount_line_candidate_summary(paddle_lines: list[str] | None, tesseract_lines: list[str] | None) -> dict[str, Any]:
    paddle_candidates = _build_amount_line_candidates('paddle', paddle_lines)
    tesseract_candidates = _build_amount_line_candidates('tesseract', tesseract_lines)
    all_candidates = paddle_candidates + tesseract_candidates
    unique_candidates, duplicate_candidates = _deduplicate_amount_line_candidates(all_candidates)
    return {
        'count': len(unique_candidates),
        'raw_count': len(all_candidates),
        'duplicate_count': len(duplicate_candidates),
        'paddle_count': len(paddle_candidates),
        'tesseract_count': len(tesseract_candidates),
        'likely_article_count': sum(1 for item in unique_candidates if item.get('likely_article_candidate')),
        'likely_non_article_count': sum(1 for item in unique_candidates if item.get('likely_non_article_candidate')),
        'candidates': unique_candidates,
        'duplicates': duplicate_candidates,
        'truncated': False,
        'scope': 'image_ocr_amount_lines_before_parser_and_store_filtering',
        'classification_scope': 'generic_store_independent_preclassification_only',
    }
'''

text = text[:start] + replacement + text[end:]

# Syntax and regex smoke test without importing the application.
compile(text, str(path), 'exec')
re.compile(r'(?<![A-Za-z0-9])(?:EUR|EURO|E|C)?\s*-?\d{1,6}(?:[\.,]\d{2})(?!\d)', re.IGNORECASE)
re.compile(r'(?<![A-Za-z0-9])\d+\s*[xX]\s*\d{1,6}(?:[\.,]\d{2})\s+\d{1,6}(?:[\.,]\d{2})(?!\d)', re.IGNORECASE)

path.write_text(text, encoding='utf-8')
print('R9-33C applied: generic candidate role signals and deduplication added')
'@

$py | python -
if ($LASTEXITCODE -ne 0) {
  Write-Error "R9-33C failed: Python patch failed"
  exit 1
}

git --no-pager diff -- backend/app/testing_receipt_line_diagnosis_routes.py

git add backend/app/testing_receipt_line_diagnosis_routes.py
git commit -m 'R9-33C add generic amount candidate role signals'
git push

Write-Host 'R9-33C toegepast en gepusht.'
