$ErrorActionPreference = 'Stop'

function Read-Utf8([string]$Path) {
  if (-not (Test-Path $Path)) { throw "Missing file: $Path" }
  [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false))
}
function Write-Utf8([string]$Path, [string]$Text) {
  [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$headerPath = Join-Path $repoRoot 'backend\app\receipt_ingestion\header_parser.py'
$servicePath = Join-Path $repoRoot 'backend\app\services\receipt_service.py'

$header = Read-Utf8 $headerPath

# Keep everything before the first AH helper / total extractor area and replace with a generic total extractor.
$startMarkers = @(
  'def _looks_like_ah_context',
  'def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:'
)
$cut = -1
foreach ($marker in $startMarkers) {
  $idx = $header.IndexOf($marker)
  if ($idx -ge 0 -and ($cut -lt 0 -or $idx -lt $cut)) { $cut = $idx }
}
if ($cut -lt 0) { throw 'R9-35B: cannot find total extraction area in header_parser.py' }
$prefix = $header.Substring(0, $cut)

# Import cleanup: generic header parser still needs _is_plausible_total_amount for non-profile totals.
if ($prefix -notmatch '_is_plausible_total_amount') {
  $prefix = $prefix.Replace("from app.receipt_ingestion.fingerprints import _is_plausible_purchase_at`n", "from app.receipt_ingestion.fingerprints import (`n    _is_plausible_purchase_at,`n    _is_plausible_total_amount,`n)`n")
}

$genericTotal = @'
def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:
    """Generic non-profile total extraction.

    Store-specific total semantics must live in store profiles. AH total
    semantics are implemented in profiles/ah/totals.py and are invoked by
    receipt_service before this generic extractor is used.
    """
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
Write-Utf8 $headerPath ($prefix + $genericTotal)

$service = Read-Utf8 $servicePath
if ($service -notmatch 'profiles\.ah\.totals') {
  $needle = "from app.receipt_ingestion.profiles.ah_runtime import build_ah_profile_article_lines, extract_positive_contributors`n"
  if (-not $service.Contains($needle)) { throw 'R9-35B: ah_runtime import not found in receipt_service.py' }
  $service = $service.Replace($needle, $needle + "from app.receipt_ingestion.profiles.ah.totals import extract_ah_total_amount, looks_like_ah_context`n")
}
$old = "    total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)"
$new = @'
    if looks_like_ah_context(text_lines, filename, store_name=store_name):
        ah_total_result = extract_ah_total_amount(text_lines, filename, store_name=store_name)
        total_amount = ah_total_result.amount
        explicit_total_found = ah_total_result.explicit_total_found
    else:
        total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)
'@
if (-not $service.Contains($old)) { throw 'R9-35B: total amount call not found in receipt_service.py' }
$service = $service.Replace($old, $new)
Write-Utf8 $servicePath $service

python -m py_compile $headerPath
python -m py_compile $servicePath
python -m py_compile (Join-Path $repoRoot 'backend\app\receipt_ingestion\profiles\ah\totals.py')

$verify = @'
from pathlib import Path
header = Path('backend/app/receipt_ingestion/header_parser.py').read_text(encoding='utf-8-sig')
for forbidden in ['_ah_strict_total_amount_from_lines', '_normalize_ah_total_anchor', 'TE BETALEN wins over TOTAAL', 'R9-34R rules']:
    if forbidden in header:
        raise SystemExit(f'AH-specific total logic remains in header_parser.py: {forbidden}')
service = Path('backend/app/services/receipt_service.py').read_text(encoding='utf-8-sig')
if 'candidate_total = line_sum +' in service:
    raise SystemExit('line-sum total fallback returned')
print('R9-35B verification passed')
'@
$verify | python -

$test = @'
from app.receipt_ingestion.profiles.ah.totals import extract_ah_total_amount
res = extract_ah_total_amount([
    'Albert Heijn',
    '2 SUBTOTAAL 5,40',
    'TE BETALEN 5,40',
    'PINNEN 5,40',
    'TOTAAL 4,95 4,95 0,45 0,45',
], 'AH foto 3.jpg', store_name='Albert Heijn')
assert str(res.amount) == '5.40', res
assert res.diagnostics['accepted_total_candidate']['raw_line'] == 'TE BETALEN 5,40'
assert any(item['reason'] == 'multiple_amounts_rejected' for item in res.diagnostics['rejected_total_candidates'])
print('R9-35B AH profile test passed')
'@
$test | docker compose exec -T backend python -

git --no-pager diff -- backend/app/receipt_ingestion/header_parser.py backend/app/services/receipt_service.py backend/app/receipt_ingestion/profiles/ah/totals.py

git add backend/app/receipt_ingestion/header_parser.py backend/app/services/receipt_service.py backend/app/receipt_ingestion/profiles/ah/totals.py tools/R9-35B_apply_header_service_wiring.ps1
git commit -m 'R9-35B wire AH total extraction profile'
git push

Write-Host 'R9-35B toegepast en gepusht.'
