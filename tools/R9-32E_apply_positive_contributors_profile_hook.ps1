$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-32E apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/receipt_ingestion/profiles/ah_runtime.py')
text = path.read_text(encoding='utf-8')

if "POSITIVE_CONTRIBUTOR_BRANCH = 'positive_savings_contribution'" not in text:
    text = text.replace(
        "AMOUNT_ONLY_RE = re.compile(r'^(?P<amount>\\d{1,5}(?:[\\.,]\\d{2}))$')\n",
        "AMOUNT_ONLY_RE = re.compile(r'^(?P<amount>\\d{1,5}(?:[\\.,]\\d{2}))$')\nPOSITIVE_CONTRIBUTOR_BRANCH = 'positive_savings_contribution'\n",
        1,
    )

if "if any('koopzegels premium' in str(line or '').lower() for line in text_lines):" not in text:
    text = text.replace(
        "    if re.search(r'\\bah\\b', haystack) and any(token in haystack for token in ('bonus', 'totaal', 'betaling', 'kassabon')):\n        return True\n    return False\n",
        "    if re.search(r'\\bah\\b', haystack) and any(token in haystack for token in ('bonus', 'totaal', 'betaling', 'kassabon')):\n        return True\n    if any('koopzegels premium' in str(line or '').lower() for line in text_lines):\n        return True\n    return False\n",
        1,
    )

insert_after = "def _extract_amounts(line: str) -> list[Decimal]:\n"
if 'def _positive_contributor_line(' not in text:
    start = text.index(insert_after)
    marker = "\n\ndef _build_savings_stamps_candidate("
    end = text.index(marker)
    positive_block = r'''

def _positive_contributor_line(*, quantity: Decimal, line_total: Decimal, source_index: int, raw_line: str | None, normalized_line: str | None, filename: str | None, store_name: str | None, hint: str) -> dict[str, Any] | None:
    if quantity <= 0 or line_total <= Decimal('0.00'):
        return None
    try:
        unit_price = (line_total / quantity).quantize(Decimal('0.01'))
    except Exception:
        unit_price = line_total
    amount_label = str(line_total).replace('.', ',')
    label = f'KOOPZEGELS PREMIUM {amount_label}'
    return {
        'raw_label': label,
        'normalized_label': label,
        'quantity': float(quantity),
        'unit': None,
        'unit_price': float(unit_price),
        'line_total': float(line_total),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': 0.94,
        'source_index': source_index,
        'producer_trace': {
            'filename': filename,
            'store_name': store_name,
            'profile': 'ah',
            'profile_hook': 'positive_contributors',
            'function_name': 'extract_positive_contributors',
            'append_branch': POSITIVE_CONTRIBUTOR_BRANCH,
            'parser_path': 'AhReceiptProfile.runtime.positive_contributors.koopzegels_premium',
            'source_index': source_index,
            'raw_line': raw_line,
            'normalized_line': normalized_line,
            'label': 'KOOPZEGELS PREMIUM',
            'display_label': 'KOOPZEGELS PREMIUM',
            'quantity': float(quantity),
            'unit_price': float(unit_price),
            'amount': float(line_total),
            'classification': 'product_candidate',
            'classification_allows_append': True,
            'append_allowed': True,
            'caller_line_hint': hint,
            'contributor_type': 'positive_total_contributor',
            'inventory_article': False,
            'status_neutral': True,
        },
    }


def _positive_contributor_from_line(line: str, *, source_index: int, following_lines: list[str], filename: str | None, store_name: str | None) -> dict[str, Any] | None:
    normalized = _norm(line)
    match = AH_SAVINGS_STAMPS_RE.match(normalized.lower())
    if match:
        try:
            quantity = Decimal(match.group('qty') or '1').quantize(Decimal('1'))
            line_total = Decimal(match.group('amount').replace(',', '.')).quantize(Decimal('0.01'))
        except Exception:
            return None
        return _positive_contributor_line(quantity=quantity, line_total=line_total, source_index=source_index, raw_line=line, normalized_line=normalized, filename=filename, store_name=store_name, hint='R9-32E AH positive_contributors same-line KOOPZEGELS PREMIUM')
    label_match = AH_SAVINGS_STAMPS_LABEL_RE.match(normalized.lower())
    if not label_match:
        return None
    quantity = Decimal(label_match.group('qty') or '1').quantize(Decimal('1'))
    for next_line in following_lines[:2]:
        next_normalized = _norm(next_line)
        amount_match = AMOUNT_ONLY_RE.match(next_normalized)
        if not amount_match:
            continue
        try:
            line_total = Decimal(amount_match.group('amount').replace(',', '.')).quantize(Decimal('0.01'))
        except Exception:
            continue
        return _positive_contributor_line(quantity=quantity, line_total=line_total, source_index=source_index, raw_line=line, normalized_line=normalized, filename=filename, store_name=store_name, hint='R9-32E AH positive_contributors adjacent-amount KOOPZEGELS PREMIUM')
    return None


def extract_positive_contributors(text_lines: list[str], existing_lines: list[dict[str, Any]], *, store_name: str | None, filename: str | None) -> list[dict[str, Any]]:
    if not _looks_like_ah_context(store_name, text_lines):
        return []
    existing_keys = set()
    for line in existing_lines or []:
        raw_label = str(line.get('raw_label') or line.get('normalized_label') or '')
        line_total = None
        try:
            if line.get('line_total') is not None:
                line_total = Decimal(str(line.get('line_total'))).quantize(Decimal('0.01'))
        except Exception:
            line_total = None
        existing_keys.add(_key(raw_label, line_total))
    generated = []
    for source_index, raw_line in enumerate(text_lines):
        candidate = _positive_contributor_from_line(raw_line, source_index=source_index, following_lines=text_lines[source_index + 1:source_index + 3], filename=filename, store_name=store_name)
        if not candidate:
            continue
        try:
            candidate_key = _key(str(candidate.get('raw_label') or ''), Decimal(str(candidate.get('line_total'))).quantize(Decimal('0.01')))
        except Exception:
            candidate_key = _key(str(candidate.get('raw_label') or ''), None)
        if candidate_key in existing_keys:
            continue
        generated.append(candidate)
        existing_keys.add(candidate_key)
    return generated
'''
    text = text[:end] + positive_block + text[end:]

if "generated: list[dict[str, Any]] = extract_positive_contributors(" not in text:
    old = "    generated: list[dict[str, Any]] = []\n    for source_index, raw_line in enumerate(text_lines):\n        following = text_lines[source_index + 1:source_index + 3]\n        parsed = (\n            _parse_ah_savings_stamps_line(raw_line)\n            or _parse_ah_savings_stamps_adjacent_amount_line(raw_line, following)\n            or _parse_ah_article_line(raw_line)\n        )\n"
    new = "    generated: list[dict[str, Any]] = extract_positive_contributors(\n        text_lines,\n        existing_lines,\n        store_name=store_name,\n        filename=filename,\n    )\n    for source_index, raw_line in enumerate(text_lines):\n        parsed = _parse_ah_article_line(raw_line)\n"
    if old not in text:
        raise SystemExit('R9-32E anchor not found for build_ah_profile_article_lines loop')
    text = text.replace(old, new, 1)

if "if 'koopzegels' in lowered:" not in text:
    text = text.replace(
        "    if any(token in lowered for token in DISCOUNT_TOKENS):\n        return None\n\n    amounts = _extract_amounts(normalized)\n",
        "    if any(token in lowered for token in DISCOUNT_TOKENS):\n        return None\n    if 'koopzegels' in lowered:\n        return None\n\n    amounts = _extract_amounts(normalized)\n",
        1,
    )

path.write_text(text, encoding='utf-8')
print('R9-32E applied: AH profile positive_contributors hook added')
'@

$py | python -

git diff -- backend/app/receipt_ingestion/profiles/ah_runtime.py

git add backend/app/receipt_ingestion/profiles/ah_runtime.py
git commit -m 'R9-32E add AH positive contributors profile hook'
git push

Write-Host 'R9-32E toegepast en gepusht.'
