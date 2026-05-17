$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8I-1B hotfix selftest-import starten...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/main.py'
if (-not (Test-Path $path)) { throw "Bestand niet gevonden: $path" }

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

if ($content -notmatch '_looks_like_false_article_metadata_line') {
    $anchor = 'from app.services.receipt_service import ('
    if (-not $content.Contains($anchor)) {
        throw 'Importblok voor app.services.receipt_service niet gevonden.'
    }
    $content = $content.Replace($anchor, "from app.services.receipt_service import (`r`n    _looks_like_false_article_metadata_line,")
} elseif ($content -match 'receipt_filter_selftest' -and $content -notmatch 'from app.services.receipt_service import \([\s\S]*_looks_like_false_article_metadata_line') {
    $anchor = 'from app.services.receipt_service import ('
    if (-not $content.Contains($anchor)) {
        throw 'Importblok voor app.services.receipt_service niet gevonden.'
    }
    $content = $content.Replace($anchor, "from app.services.receipt_service import (`r`n    _looks_like_false_article_metadata_line,")
}

if ($content -ne $original) {
    Copy-Item $path "$path.8i1b-import-hotfix-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Import voor _looks_like_false_article_metadata_line toegevoegd.' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast; import lijkt al aanwezig.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna GET /api/testing/receipt-filter-selftest opnieuw uitvoeren.' -ForegroundColor Yellow
