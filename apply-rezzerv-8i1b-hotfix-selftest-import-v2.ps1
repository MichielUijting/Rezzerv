$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8I-1B hotfix selftest-import v2 starten...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/main.py'
if (-not (Test-Path $path)) { throw "Bestand niet gevonden: $path" }

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

$importLine = 'from app.services.receipt_service import _looks_like_false_article_metadata_line'
if ($content -notmatch [regex]::Escape($importLine)) {
    $content = $importLine + "`r`n" + $content
}

if ($content -ne $original) {
    Copy-Item $path "$path.8i1b-import-hotfix-v2-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Zelfstandige importregel toegevoegd bovenaan main.py.' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast; importregel lijkt al aanwezig.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna GET /api/testing/receipt-filter-selftest opnieuw uitvoeren.' -ForegroundColor Yellow
