$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$path = Join-Path $root 'backend/app/main.py'
if (-not (Test-Path $path)) {
    throw "Bestand niet gevonden: $path"
}

$content = Get-Content $path -Raw

if ($content -notmatch 'receipt_import_diagnosis_routes') {
    $content = $content -replace 'from app.api.receipt_kpi_routes import router as receipt_kpi_router', "from app.api.receipt_kpi_routes import router as receipt_kpi_router`r`nfrom app.api.receipt_import_diagnosis_routes import router as receipt_import_diagnosis_router"
}

if ($content -notmatch 'app.include_router\(receipt_import_diagnosis_router\)') {
    $content = $content -replace 'app.include_router\(receipt_kpi_router\)', "app.include_router(receipt_kpi_router)`r`napp.include_router(receipt_import_diagnosis_router)"
}

Set-Content $path $content -Encoding UTF8

Write-Host ''
Write-Host 'Receipt import diagnosis router geactiveerd.' -ForegroundColor Green
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
