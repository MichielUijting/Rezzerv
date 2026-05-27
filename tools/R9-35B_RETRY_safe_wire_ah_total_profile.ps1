$ErrorActionPreference = 'Stop'

function Read-Utf8([string]$Path) {
  if (-not (Test-Path $Path)) { throw "Missing file: $Path" }
  return [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false))
}

function Write-Utf8([string]$Path, [string]$Text) {
  [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}

function Show-MatchContext([string]$Path, [string]$Pattern, [int]$Before = 4, [int]$After = 6) {
  $lines = [System.IO.File]::ReadAllLines($Path, [System.Text.UTF8Encoding]::new($false))
  for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i].Contains($Pattern)) {
      $start = [Math]::Max(0, $i - $Before)
      $end = [Math]::Min($lines.Length - 1, $i + $After)
      for ($j = $start; $j -le $end; $j++) {
        $marker = if ($j -eq $i) { '>>' } else { '  ' }
        Write-Host ("{0} {1,5}: {2}" -f $marker, ($j + 1), $lines[$j])
      }
      return
    }
  }
  throw "Pattern not found for context: $Pattern"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$servicePath = Join-Path $repoRoot 'backend\app\services\receipt_service.py'
$totalsPath = Join-Path $repoRoot 'backend\app\receipt_ingestion\profiles\ah\totals.py'
$headerPath = Join-Path $repoRoot 'backend\app\receipt_ingestion\header_parser.py'

Write-Host 'R9-35B-RETRY pre-check: current total_amount context'
Show-MatchContext $servicePath 'total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)'

$service = Read-Utf8 $servicePath

$importLine = 'from app.receipt_ingestion.profiles.ah.totals import extract_ah_total_amount, looks_like_ah_context'
$importCount = ([regex]::Matches($service, [regex]::Escape($importLine))).Count
if ($importCount -eq 0) {
  $ahRuntimePattern = 'from app.receipt_ingestion.profiles.ah_runtime import build_ah_profile_article_lines, extract_positive_contributors'
  if (-not $service.Contains($ahRuntimePattern)) {
    throw 'R9-35B-RETRY failed: safe import insertion point not found'
  }
  $service = $service.Replace($ahRuntimePattern, $ahRuntimePattern + "`n" + $importLine)
} elseif ($importCount -gt 1) {
  throw "R9-35B-RETRY failed: AH totals import occurs $importCount times"
}

$oldLine = '    total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)'
$oldCount = ([regex]::Matches($service, [regex]::Escape($oldLine))).Count
if ($oldCount -ne 1) {
  throw "R9-35B-RETRY failed: expected exactly one generic total assignment, found $oldCount"
}

$newBlock = @'
    if looks_like_ah_context(text_lines, filename, store_name=store_name):
        ah_total_result = extract_ah_total_amount(text_lines, filename, store_name=store_name)
        total_amount = ah_total_result.amount
        explicit_total_found = ah_total_result.explicit_total_found
    else:
        total_amount, explicit_total_found = _total_amount_from_lines(text_lines, filename)
'@

$service = $service.Replace($oldLine, $newBlock.TrimEnd("`r", "`n"), 1)
Write-Utf8 $servicePath $service

Write-Host 'R9-35B-RETRY post-change: AH dispatch context'
Show-MatchContext $servicePath 'if looks_like_ah_context(text_lines, filename, store_name=store_name):'

python -m py_compile $servicePath
python -m py_compile $totalsPath
python -m py_compile $headerPath

$serviceAfter = Read-Utf8 $servicePath
foreach ($forbidden in @('candidate_total = line_sum +', 'total_amount = candidate_total.quantize', 'total_amount = line_sum.quantize')) {
  if ($serviceAfter.Contains($forbidden)) {
    throw "R9-35B-RETRY failed: forbidden fallback returned: $forbidden"
  }
}
$importCountAfter = ([regex]::Matches($serviceAfter, [regex]::Escape($importLine))).Count
if ($importCountAfter -ne 1) {
  throw "R9-35B-RETRY failed: AH totals import count after change = $importCountAfter"
}
if (-not $serviceAfter.Contains('extract_ah_total_amount(text_lines, filename, store_name=store_name)')) {
  throw 'R9-35B-RETRY failed: AH profile dispatch missing after change'
}

Write-Host 'R9-35B-RETRY static verification passed.'
Write-Host 'Now rebuilding and checking backend startup...'

docker compose up --build -d
Start-Sleep -Seconds 5
$logs = docker compose logs backend --tail=80
Write-Host $logs
if ($logs -notmatch 'Application startup complete') {
  throw 'R9-35B-RETRY failed: backend did not reach Application startup complete'
}

try {
  $response = Invoke-WebRequest http://localhost:8011/docs -UseBasicParsing
  if ($response.StatusCode -ne 200) {
    throw "Unexpected /docs status: $($response.StatusCode)"
  }
  Write-Host '/docs status: 200 OK'
} catch {
  throw "R9-35B-RETRY failed: /docs not reachable: $($_.Exception.Message)"
}

git --no-pager diff -- backend/app/services/receipt_service.py

git add backend/app/services/receipt_service.py tools/R9-35B_RETRY_safe_wire_ah_total_profile.ps1
git commit -m 'R9-35B wire AH total profile safely'
git push

Write-Host 'R9-35B-RETRY toegepast, getest en gepusht.'
