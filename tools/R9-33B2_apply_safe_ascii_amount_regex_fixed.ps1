$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-33B2 apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path
import re

path = Path('backend/app/testing_receipt_line_diagnosis_routes.py')
text = path.read_text(encoding='utf-8')

start_marker = 'AMOUNT_LINE_PATTERN = re.compile('
end_marker = '\n\ndef _extract_ocr_amounts'

if start_marker not in text:
    raise SystemExit('R9-33B2 failed: AMOUNT_LINE_PATTERN anchor not found')

start = text.index(start_marker)
end = text.index(end_marker, start)

replacement = r'''AMOUNT_LINE_PATTERN = re.compile(
    # ASCII-only on purpose: OCR/report scripts have shown currency symbols can be mojibaked.
    # This layer only detects amount-bearing lines; store-specific interpretation comes later.
    r'(?<![A-Za-z0-9])(?:EUR|EURO|E|C)?\s*-?\d{1,6}(?:[\.,]\d{2})(?!\d)',
    re.IGNORECASE,
)
COMPACT_AMOUNT_LINE_PATTERN = re.compile(
    r'(?<![A-Za-z0-9])\d+\s*[xX]\s*\d{1,6}(?:[\.,]\d{2})\s+\d{1,6}(?:[\.,]\d{2})(?!\d)',
    re.IGNORECASE,
)


def _normalize_ocr_amount_token(value: str | None) -> str:
    token = re.sub(r'\s+', '', str(value or '').strip())
    token = re.sub(r'^(?:EUR|EURO|E|C)', '', token, flags=re.IGNORECASE)
    return token
'''

# Compile-test only the raw regex strings. Do not exec project functions or type hints.
re.compile(r'(?<![A-Za-z0-9])(?:EUR|EURO|E|C)?\s*-?\d{1,6}(?:[\.,]\d{2})(?!\d)', re.IGNORECASE)
re.compile(r'(?<![A-Za-z0-9])\d+\s*[xX]\s*\d{1,6}(?:[\.,]\d{2})\s+\d{1,6}(?:[\.,]\d{2})(?!\d)', re.IGNORECASE)

text = text[:start] + replacement + text[end:]
path.write_text(text, encoding='utf-8')
print('R9-33B2 applied: safe ASCII amount regex fixed and compile-tested')
'@

$py | python -
if ($LASTEXITCODE -ne 0) {
  Write-Error "R9-33B2 failed: Python patch failed"
  exit 1
}

git --no-pager diff -- backend/app/testing_receipt_line_diagnosis_routes.py

git add backend/app/testing_receipt_line_diagnosis_routes.py
git commit -m 'R9-33B2 fix safe ASCII amount regex apply script'
git push

Write-Host 'R9-33B2 toegepast en gepusht.'
