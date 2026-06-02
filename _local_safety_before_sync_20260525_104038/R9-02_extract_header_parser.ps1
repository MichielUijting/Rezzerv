$ErrorActionPreference = 'Stop'

$mainPath = 'backend\app\services\receipt_service.py'
$headerPath = 'backend\app\receipt_ingestion\header_parser.py'

if (!(Test-Path $mainPath)) { throw "Niet gevonden: $mainPath" }
if (!(Test-Path $headerPath)) { throw "Niet gevonden: $headerPath" }

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = "$mainPath.R9-02_header_parser_backup_$timestamp"
Copy-Item $mainPath $backupPath -Force
Write-Host "Backup gemaakt: $backupPath"

$content = Get-Content $mainPath -Raw -Encoding UTF8

$importBlock = @'
from app.receipt_ingestion.header_parser import (
    _looks_like_store_branch_line,
    _purchase_at_from_lines,
    _store_branch_from_lines,
    _store_from_text,
    _total_amount_from_lines,
)

'@

if (!$content.Contains('from app.receipt_ingestion.header_parser import')) {
  $anchor = @'
from app.receipt_ingestion.fingerprints import (
    _build_receipt_fingerprint,
    _is_plausible_purchase_at,
    _is_plausible_total_amount,
    _normalize_fingerprint_text,
    build_receipt_fingerprint_from_parse_result,
)

'@
  if (!$content.Contains($anchor)) {
    throw 'Import-anchor niet gevonden; stop.'
  }
  $content = $content.Replace($anchor, $anchor + $importBlock)
}

$functionNames = @(
  '_store_from_text',
  '_looks_like_store_branch_line',
  '_store_branch_from_lines',
  '_purchase_at_from_lines',
  '_total_amount_from_lines'
)

foreach ($name in $functionNames) {
  $pattern = "(?ms)^def $name\([\s\S]*?)(?=^def |\Z)"
  $matches = [regex]::Matches($content, $pattern)
  if ($matches.Count -ne 1) {
    throw "Verwacht precies 1 functieblok voor $name, gevonden: $($matches.Count)"
  }
  $content = [regex]::Replace($content, $pattern, '', 1)
  Write-Host "Verwijderd uit receipt_service.py: $name"
}

[System.IO.File]::WriteAllText($mainPath, $content, [System.Text.UTF8Encoding]::new($false))

Write-Host ''
Write-Host 'Controle resterende functie-definities in receipt_service.py:'
foreach ($name in $functionNames) {
  $remaining = Select-String -Path $mainPath -Pattern "def $name" -SimpleMatch
  if ($remaining) {
    throw "Functie $name staat nog in receipt_service.py"
  }
}
Write-Host 'OK: headerfuncties zijn uit receipt_service.py verwijderd.'

Write-Host ''
Write-Host 'Controle import:'
Select-String -Path $mainPath -Pattern 'receipt_ingestion.header_parser'

Write-Host ''
Write-Host 'Volgende commando’s:'
Write-Host 'python -m py_compile backend\app\receipt_ingestion\header_parser.py backend\app\services\receipt_service.py'
Write-Host 'git add backend\app\receipt_ingestion\header_parser.py backend\app\services\receipt_service.py'
Write-Host 'git commit -m "R9-02 Extract receipt header parser"'
Write-Host 'git push'
