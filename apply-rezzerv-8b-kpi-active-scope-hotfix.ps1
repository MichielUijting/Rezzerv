$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$routePath = Join-Path $root 'backend/app/api/receipt_kpi_routes.py'
if (-not (Test-Path $routePath)) {
    throw "Bestand niet gevonden: $routePath"
}

$content = Get-Content $routePath -Raw

$content = $content -replace 'from receipt_ingestion\.kassa_kpi_baseline import build_kassa_kpi_baseline', 'from receipt_ingestion.kassa_active_scope_kpi import build_active_kassa_scope_kpi'
$content = $content -replace 'return build_kassa_kpi_baseline\(conn\)', 'return build_active_kassa_scope_kpi(conn)'
$content = $content -replace 'Read-only KPI summary for the existing Kassa/SSOT flow\.', 'Read-only KPI summary using the same active receipt scope as Kassa.'

Set-Content $routePath $content -Encoding UTF8

Write-Host ''
Write-Host 'Rezzerv 8B KPI active-scope hotfix toegepast.' -ForegroundColor Green
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
