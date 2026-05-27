$ErrorActionPreference = 'Stop'

function Read-Utf8File([string]$Path) {
  if (-not (Test-Path $Path)) { throw "Bestand ontbreekt: $Path" }
  return [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false))
}

function Write-Utf8File([string]$Path, [string]$Content) {
  [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$headerPath = Join-Path $repoRoot 'backend\app\receipt_ingestion\header_parser.py'
$text = Read-Utf8File $headerPath

$pattern = '(?s)def _ah_strict_total_amount_from_lines\(lines: list\[str\]\) -> tuple\[Decimal \| None, bool\]:.*?(?=\n\ndef _total_amount_from_lines)'
$replacement = @'
def _ah_strict_total_amount_from_lines(lines: list[str]) -> tuple[Decimal | None, bool]:
    """AH total extraction from exact total anchors only.

    R9-34R rules:
    - TE BETALEN wins over TOTAAL.
    - The anchor is valid only when removing the single amount leaves exactly
      TE BETALEN or TOTAAL.
    - Lines with multiple amounts are rejected as checkout total candidates,
      which excludes VAT summary lines such as TOTAAL 4,95 4,95 0,45 0,45.
    - The article line sum is never used as a source for total_amount.
    """
    candidates: list[tuple[int, int, Decimal, bool]] = []

    def _candidate_priority(anchor: str) -> int:
        return 200 if anchor == 'TE BETALEN' else 100

    def _empty_after_amount_removal(value: str | None) -> bool:
        return _normalize_ah_total_anchor(_line_without_amounts(value)) == ''

    for index, raw_line in enumerate(lines):
        line = str(raw_line or '').strip()
        if not line:
            continue

        # Same-line form, e.g. TE BETALEN 5,40 or TOTAAL 8,28.
        # Reject multi-amount lines because AH VAT totals use this shape.
        same_line_amounts = _amounts_from_text(line)
        if same_line_amounts:
            if len(same_line_amounts) != 1:
                continue
            anchor_after_amount_removal = _normalize_ah_total_anchor(_line_without_amounts(line))
            if anchor_after_amount_removal in {'TOTAAL', 'TE BETALEN'}:
                candidates.append((
                    _candidate_priority(anchor_after_amount_removal),
                    index,
                    same_line_amounts[0],
                    True,
                ))
            continue

        # Separate-line form: the anchor line itself must be exact and the
        # direct next line must contain exactly one amount with no text residue.
        anchor = _normalize_ah_total_anchor(line)
        if anchor not in {'TOTAAL', 'TE BETALEN'}:
            continue
        if index + 1 >= len(lines):
            continue

        next_line = str(lines[index + 1] or '').strip()
        next_amounts = _amounts_from_text(next_line)
        if len(next_amounts) != 1:
            continue
        if not _empty_after_amount_removal(next_line):
            continue

        candidates.append((_candidate_priority(anchor), index, next_amounts[0], True))

    if not candidates:
        return None, False

    # Highest priority wins. For equal priority, keep the earliest matching
    # anchor because later AH TOTAAL lines are usually payment/VAT details.
    candidates.sort(key=lambda item: (-item[0], item[1]))
    chosen = candidates[0]
    return chosen[2], chosen[3]
'@

$matches = [regex]::Matches($text, $pattern)
if ($matches.Count -ne 1) {
  throw "R9-34R patch failed: expected exactly one AH strict total function, found $($matches.Count)"
}
$text = [regex]::Replace($text, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $replacement }, 1)
Write-Utf8File $headerPath $text

python -m py_compile $headerPath

$test = @'
from app.receipt_ingestion.header_parser import _total_amount_from_lines

def assert_total(name, lines, expected):
    amount, explicit = _total_amount_from_lines(lines, name)
    assert str(amount) == expected, (name, amount, expected)
    assert explicit is True

assert_total('AH foto 3.jpg', [
    'Albert Heijn',
    '2 SUBTOTAAL 5,40',
    'JE VOORDEEL waarvan 0,00',
    'TE BETALEN 5,40',
    'PINNEN 5,40',
    'TOTAAL 4,95 4,95 0,45 0,45',
], '5.40')

assert_total('AH foto 2.jpeg', [
    'Albert Heijn Ger Koopman',
    '2 SUBTOTAAL 8,28',
    'TOTAAL 8,28',
    'PINNEN 8,28',
    'Totaal 8,28 EUR Contactless',
    'TOTAAL 7,60 0,68',
], '8.28')

assert_total('AH foto 1.pdf', [
    'Albert Heijn',
    'SUBTOTAAL 41,07',
    'TOTAAL 49,27',
    'PINNEN 49,27',
    'TOTAAL 36,82 4,25',
], '49.27')

print('R9-34R AH total anchor tests passed')
'@
$test | docker compose exec -T backend python -

Write-Host 'R9-34R applied:'
Write-Host '- AH TE BETALEN wins over TOTAAL'
Write-Host '- multi-amount TOTAAL lines are rejected as VAT-summary candidates'
Write-Host '- AH total still comes only from exact total anchors after amount removal'

git --no-pager diff -- backend/app/receipt_ingestion/header_parser.py

git add backend/app/receipt_ingestion/header_parser.py tools/R9-34R_apply_ah_total_anchor_priority_fix.ps1
git commit -m 'R9-34R fix AH total anchor priority'
git push

Write-Host 'R9-34R toegepast en gepusht.'
