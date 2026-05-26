$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-34C apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/receipt_ingestion/profiles/ah_runtime.py')
text = path.read_text(encoding='utf-8')

old = """    raw = str(line or '').strip()
    norm = _norm(raw)
    non_product_reasons: list[str] = []
"""
new = """    raw = str(line or '').strip()
    norm = _norm(raw).lower()
    non_product_reasons: list[str] = []
"""
if old not in text:
    raise SystemExit('R9-34C failed: normalization anchor not found')
text = text.replace(old, new, 1)

old_tokens = """    if any(token in norm for token in ('subtotaal', 'totaal', 'te betalen', 'betalen')):
        non_product_reasons.append('ah_total_or_payment_total_line')
    if any(token in norm for token in ('pinnen', 'pin ', 'v pay', 'v-pay', 'betaling', 'betaald met')):
        non_product_reasons.append('ah_payment_line')
    if any(token in norm for token in ('app deals', 'bonus', 'voordeel', 'korting')):
        non_product_reasons.append('ah_promotion_or_advantage_line')
    if any(token in norm for token in ('btw', 'over', 'eur')) and len(_extract_amounts(raw)) >= 2:
        non_product_reasons.append('ah_vat_or_tax_line')
"""
new_tokens = """    if any(token in norm for token in ('subtotaal', 'totaal', 'te betalen', 'betalen')):
        non_product_reasons.append('ah_total_or_payment_total_line')
    if any(token in norm for token in ('pinnen', 'pin ', 'v pay', 'v-pay', 'betaling', 'betaald met')):
        non_product_reasons.append('ah_payment_line')
    if any(token in norm for token in ('app deals', 'bonus', 'voordeel', 'korting', 'actie', 'gratis')):
        non_product_reasons.append('ah_promotion_or_advantage_line')
    if any(token in norm for token in ('btw', 'bedr.excl', 'bedr. excl', 'bedr.incl', 'bedr. incl', 'eur')) and len(_extract_amounts(raw)) >= 2:
        non_product_reasons.append('ah_vat_or_tax_line')
"""
if old_tokens not in text:
    raise SystemExit('R9-34C failed: token block anchor not found')
text = text.replace(old_tokens, new_tokens, 1)

compile(text, str(path), 'exec')

# Minimal local smoke test for the exact AH helper behavior without importing the app.
namespace = {}
exec(text, namespace, namespace)
check = namespace['_ah_candidate_selection_reason']
assert check('Ì CHAUDF WATER 1,80')['is_ah_product_candidate'] is True
assert check('1 AH SANDWICH 3,60')['is_ah_product_candidate'] is True
for sample in ['2 SUBTOTAAL 5,40', 'JE VOORDEEL 0,00', 'App Deals 0,00', 'TE BETALEN 5,40', 'PINNEN 5,40', 'BTW TOTAAL 4,95 0,45']:
    result = check(sample)
    assert result['is_ah_non_product_candidate'] is True, (sample, result)
    assert result['is_ah_product_candidate'] is False, (sample, result)

path.write_text(text, encoding='utf-8')
print('R9-34C applied: AH candidate selection is case-insensitive and smoke-tested')
'@

$py | python -
if ($LASTEXITCODE -ne 0) {
  Write-Error "R9-34C failed: Python patch failed"
  exit 1
}

git --no-pager diff -- backend/app/receipt_ingestion/profiles/ah_runtime.py
git add backend/app/receipt_ingestion/profiles/ah_runtime.py
git commit -m 'R9-34C fix AH candidate selection normalization'
git push
Write-Host 'R9-34C toegepast en gepusht.'
