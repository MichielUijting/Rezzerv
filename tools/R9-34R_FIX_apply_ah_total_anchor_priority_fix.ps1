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

$marker = 'def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:'
$start = $text.IndexOf($marker)
if ($start -lt 0) {
  throw 'R9-34R-FIX failed: _total_amount_from_lines niet gevonden'
}

$prefix = $text.Substring(0, $start)
$replacement = @'
def _looks_like_ah_context(lines: list[str], filename: str) -> bool:
    haystack = ' '.join(str(line or '') for line in lines[:20]).lower()
    lower_filename = str(filename or '').lower()
    return (
        'ah ' in lower_filename
        or 'ah_' in lower_filename
        or 'albert heijn' in haystack
        or 'ah to go' in haystack
        or re.search(r'\bah\b', haystack) is not None
    )


def _normalize_ah_total_anchor(value: str | None) -> str:
    normalized = str(value or '').upper()
    normalized = re.sub(r'[^A-Z\s]+', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def _amounts_from_text(value: str | None) -> list[Decimal]:
    amounts: list[Decimal] = []
    for match in re.finditer(r'(?<!\d)(-?\d{1,6}(?:[\.,]\d{2}))(?!\d)', str(value or '')):
        parsed = _parse_decimal(match.group(1))
        if parsed is not None and _is_plausible_total_amount(parsed):
            amounts.append(parsed)
    return amounts


def _line_without_amounts(value: str | None) -> str:
    cleaned = re.sub(r'(?<!\d)-?\d{1,6}(?:[\.,]\d{2})(?!\d)', ' ', str(value or ''))
    cleaned = re.sub(r'\b(?:EUR|EURO)\b|€', ' ', cleaned, flags=re.IGNORECASE)
    return cleaned


def _ah_strict_total_amount_from_lines(lines: list[str]) -> tuple[Decimal | None, bool]:
    """AH total extraction from exact total anchors only.

    R9-34R rules:
    - TE BETALEN wins over TOTAAL.
    - The anchor is valid only when removing exactly one amount leaves exactly
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

    candidates.sort(key=lambda item: (-item[0], item[1]))
    chosen = candidates[0]
    return chosen[2], chosen[3]


def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:
    if _looks_like_ah_context(lines, filename):
        return _ah_strict_total_amount_from_lines(lines)

    amount_pattern = re.compile(r'(-?\d{1,6}(?:[\.,]\d{2}))')
    explicit_total_pattern = re.compile(r'(?i)\b(totaal|te betalen|te voldoen|eindtotaal|total due|amount due)\b')
    subtotal_pattern = re.compile(r'(?i)\b(subtotaal|subtotal)\b')
    payment_pattern = re.compile(r'(?i)\b(bankpas|pinnen|pin|betaald|betaling)\b')
    vat_pattern = re.compile(r'(?i)\b(btw|bedr\.excl|bedr\.incl|bedrag excl|bedrag incl)\b')
    refund_pattern = re.compile(r'(?i)\b(retour|refund|credit)\b')
    candidates: list[tuple[int, int, Decimal, bool]] = []
    in_vat_block = False

    for index, line in enumerate(lines):
        lowered = str(line or '').lower()
        if vat_pattern.search(lowered) or lowered.startswith('%'):
            in_vat_block = True
        matches = amount_pattern.findall(str(line or ''))
        parsed_matches = [_parse_decimal(item) for item in matches]
        parsed_matches = [item for item in parsed_matches if item is not None]
        if not parsed_matches:
            continue
        if subtotal_pattern.search(lowered):
            continue
        if any(token in lowered for token in ('voordeel', 'korting', 'waarvan', 'bonus box')):
            continue
        explicit = bool(explicit_total_pattern.search(lowered))
        payment = bool(payment_pattern.search(lowered))
        if not explicit and not payment:
            continue
        amount = parsed_matches[-1]
        score = 0
        if explicit:
            score += 40
        if payment:
            score += 25
        if 'eur' in lowered:
            score += 10
        if in_vat_block or vat_pattern.search(lowered):
            score -= 100
        if refund_pattern.search(lowered):
            score -= 60
        if len(parsed_matches) > 1:
            score -= 10 * (len(parsed_matches) - 1)
        if _is_plausible_total_amount(amount):
            candidates.append((score, index, amount, explicit))

    if not candidates:
        return None, False
    valid_candidates = [candidate for candidate in candidates if candidate[0] > 0]
    chosen = sorted(valid_candidates or candidates, key=lambda item: (item[0], item[1]))[-1]
    return chosen[2], chosen[3]
'@

$newText = $prefix + $replacement
Write-Utf8File $headerPath $newText
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

print('R9-34R-FIX AH total anchor tests passed')
'@
$test | docker compose exec -T backend python -

Write-Host 'R9-34R-FIX applied:'
Write-Host '- AH TE BETALEN wins over TOTAAL'
Write-Host '- multi-amount TOTAAL lines are rejected as VAT-summary candidates'
Write-Host '- AH total still comes only from exact total anchors after amount removal'

git --no-pager diff -- backend/app/receipt_ingestion/header_parser.py

git add backend/app/receipt_ingestion/header_parser.py tools/R9-34R_FIX_apply_ah_total_anchor_priority_fix.ps1
git commit -m 'R9-34R fix AH total anchor priority robustly'
git push

Write-Host 'R9-34R-FIX toegepast en gepusht.'
