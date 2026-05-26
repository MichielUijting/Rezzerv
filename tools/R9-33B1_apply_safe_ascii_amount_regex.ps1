$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-33B1 apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/testing_receipt_line_diagnosis_routes.py')
text = path.read_text(encoding='utf-8')

start = text.index('AMOUNT_LINE_PATTERN = re.compile(')
end = text.index('\n\ndef _extract_ocr_amounts', start)
replacement = r'''AMOUNT_LINE_PATTERN = re.compile(
    # ASCII-only on purpose: uploaded OCR/debug scripts have shown currency symbols can be mojibaked.
    # We detect amounts broadly first; store-specific interpretation comes later.
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
text = text[:start] + replacement + text[end:]

# Compile-test the exact regexes after replacement before committing.
namespace = {}
probe = "import re\n" + text[text.index('AMOUNT_LINE_PATTERN = re.compile('):text.index('\n\ndef _line_summary', text.index('AMOUNT_LINE_PATTERN = re.compile('))]
exec(probe, namespace, namespace)

path.write_text(text, encoding='utf-8')
print('R9-33B1 applied: amount regex is ASCII-safe and compile-tested')
'@

$py | python -

git --no-pager diff -- backend/app/testing_receipt_line_diagnosis_routes.py

git add backend/app/testing_receipt_line_diagnosis_routes.py
git commit -m 'R9-33B1 use safe ASCII amount regex'
git push

Write-Host 'R9-33B1 toegepast en gepusht.'
