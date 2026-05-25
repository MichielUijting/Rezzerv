param([switch]$NoCommit)
$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-31C apply failed: verkeerde branch: $branch"
  exit 1
}

$python = @'
from pathlib import Path

path = Path('backend/app/receipt_ingestion/profiles/ah_runtime.py')
text = path.read_text(encoding='utf-8-sig')

# 1. Maak KOOPZEGELS expliciet herkenbaar als positieve AH total contributor.
if 'AH_SAVINGS_STAMPS_RE' not in text:
    anchor = "DISCOUNT_TOKENS = ('bonus', 'korting', 'persoonlijke bonus', 'bonus box', 'uw voordeel')\n"
    replacement = anchor + "AH_SAVINGS_STAMPS_RE = re.compile(r'^(?P<qty>\\d+)\\s+koopzegels(?:\\s+premium)?\\s+(?P<amount>\\d{1,5}(?:[\\.,]\\d{2}))$', re.I)\n"
    if anchor not in text:
        raise SystemExit('R9-31C apply failed: DISCOUNT_TOKENS-anchor niet gevonden')
    text = text.replace(anchor, replacement, 1)

# 2. Voeg parserfunctie toe vóór gewone AH artikelparser.
if 'def _parse_ah_savings_stamps_line' not in text:
    anchor = "\ndef _parse_ah_article_line(line: str) -> dict[str, Any] | None:\n"
    insert = r'''
def _parse_ah_savings_stamps_line(line: str) -> dict[str, Any] | None:
    normalized = _norm(line)
    match = AH_SAVINGS_STAMPS_RE.match(normalized.lower())
    if not match:
        return None
    try:
        quantity = Decimal(match.group('qty')).quantize(Decimal('1'))
        line_total = Decimal(match.group('amount').replace(',', '.')).quantize(Decimal('0.01'))
    except Exception:
        return None
    if quantity <= 0 or line_total <= Decimal('0.00'):
        return None
    try:
        unit_price = (line_total / quantity).quantize(Decimal('0.01'))
    except Exception:
        unit_price = line_total
    return {
        'label': 'KOOPZEGELS PREMIUM',
        'quantity': float(quantity),
        'unit': None,
        'unit_price': unit_price,
        'line_total': line_total,
        'append_branch': 'ah_koopzegels_premium_detected',
        'parser_path': 'AhReceiptProfile.runtime.savings_stamps_positive_contributor',
        'caller_line_hint': 'R9-31C AH koopzegels positive total contributor',
        'confidence_score': 0.91,
    }

'''
    if anchor not in text:
        raise SystemExit('R9-31C apply failed: _parse_ah_article_line-anchor niet gevonden')
    text = text.replace(anchor, insert + anchor, 1)

# 3. Gebruik koopzegelparser vóór gewone artikelparser.
old = "        parsed = _parse_ah_article_line(raw_line)\n        if not parsed:\n            continue\n"
new = "        parsed = _parse_ah_savings_stamps_line(raw_line) or _parse_ah_article_line(raw_line)\n        if not parsed:\n            continue\n"
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit('R9-31C apply failed: parsed-regel niet gevonden')

# 4. Gebruik R9-31C tracevelden als aanwezig.
old_block = """            function_name='build_ah_profile_article_lines',
            append_branch='ah_profile_safe_article_line',
            parser_path='AhReceiptProfile.runtime.safe_article_line',
            caller_line_hint='R9-31B AH profile safe article construction',
"""
new_block = """            function_name='build_ah_profile_article_lines',
            append_branch=str(parsed.get('append_branch') or 'ah_profile_safe_article_line'),
            parser_path=str(parsed.get('parser_path') or 'AhReceiptProfile.runtime.safe_article_line'),
            caller_line_hint=str(parsed.get('caller_line_hint') or 'R9-31B AH profile safe article construction'),
"""
if old_block in text:
    text = text.replace(old_block, new_block, 1)
elif new_block not in text:
    raise SystemExit('R9-31C apply failed: traceblok niet gevonden')

old_conf = "            confidence_score=0.82,\n"
new_conf = "            confidence_score=float(parsed.get('confidence_score') or 0.82),\n"
if old_conf in text:
    text = text.replace(old_conf, new_conf, 1)
elif new_conf not in text:
    raise SystemExit('R9-31C apply failed: confidence_score niet gevonden')

path.write_text(text, encoding='utf-8')
print('R9-31C patch toegepast op ah_runtime.py')
'@

$python | python -

git diff -- backend/app/receipt_ingestion/profiles/ah_runtime.py

if (-not $NoCommit) {
  git add backend/app/receipt_ingestion/profiles/ah_runtime.py
  git commit -m 'R9-31C add AH savings stamps reconciliation contributor'
  git push
  Write-Host 'R9-31C commit gepusht.'
} else {
  Write-Host 'NoCommit gebruikt; commit/push overgeslagen.'
}
