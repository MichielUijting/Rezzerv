$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8H-2 rollback upload-regressie starten...' -ForegroundColor Cyan

$frontendPath = Join-Path $root 'frontend/src/features/receipts/KassaPage.jsx'
$backendPath = Join-Path $root 'backend/app/services/receipt_service.py'
$mainPath = Join-Path $root 'backend/app/main.py'

foreach ($path in @($frontendPath, $backendPath, $mainPath)) {
    if (-not (Test-Path $path)) { throw "Bestand niet gevonden: $path" }
}

# 1. Frontend rollback: verwijder client_imported_at uit FormData en helper.
$frontend = Get-Content $frontendPath -Raw -Encoding UTF8
$frontendOriginal = $frontend

$frontend = $frontend -replace "(?s)\r?\nfunction getClientImportedAt\(\) \{.*?\r?\n\}\r?\n(?=\r?\nfunction loadStoredReceiptIds)", "`r`n"
$frontend = $frontend -replace "(?m)^\s*formData\.append\('client_imported_at', getClientImportedAt\(\)\)\r?\n", ''

if ($frontend -ne $frontendOriginal) {
    Copy-Item $frontendPath "$frontendPath.8h2-rollback-backup" -Force
    Set-Content $frontendPath $frontend -Encoding UTF8
    Write-Host 'Frontend uploadvelden hersteld.' -ForegroundColor Green
} else {
    Write-Host 'Frontend bevatte geen client_imported_at wijzigingen meer.' -ForegroundColor Yellow
}

# 2. Backend service rollback: behoud systeemdatumfallback, verwijder client_imported_at uit ingest signature en helper.
$backend = Get-Content $backendPath -Raw -Encoding UTF8
$backendOriginal = $backend

$backend = $backend.Replace(
    "def _purchase_at_or_system_date(value: str | None, client_imported_at: str | None = None) -> str:",
    "def _purchase_at_or_system_date(value: str | None) -> str:"
)
$backend = $backend -replace "(?s)\s*client_value = str\(client_imported_at or ''\)\.strip\(\)\r?\n\s*if client_value:\r?\n\s*return client_value\r?\n", "`r`n"
$backend = $backend.Replace(
    "return datetime.utcnow().astimezone().replace(microsecond=0).isoformat()",
    "return datetime.utcnow().date().isoformat()"
)
$backend = $backend.Replace(
    ", failed_purchase_at: str | None = None, client_imported_at: str | None = None) -> dict[str, Any]:",
    ", failed_purchase_at: str | None = None) -> dict[str, Any]:"
)
$backend = $backend.Replace(
    "table_purchase_at = _purchase_at_or_system_date(parse_result.purchase_at if parse_result.is_receipt else failed_purchase_at, client_imported_at)",
    "table_purchase_at = _purchase_at_or_system_date(parse_result.purchase_at if parse_result.is_receipt else failed_purchase_at)"
)

if ($backend -ne $backendOriginal) {
    Copy-Item $backendPath "$backendPath.8h2-rollback-backup" -Force
    Set-Content $backendPath $backend -Encoding UTF8
    Write-Host 'Backend ingest signature hersteld.' -ForegroundColor Green
} else {
    Write-Host 'Backend service bevatte geen client_imported_at wijzigingen meer.' -ForegroundColor Yellow
}

# 3. main.py rollback: verwijder client_imported_at Form-parameters en doorgeefregels.
$main = Get-Content $mainPath -Raw -Encoding UTF8
$mainOriginal = $main

$main = $main -replace "(?m)^\s*client_imported_at:\s*str \| None = Form\(None\),\r?\n", ''
$main = $main -replace "(?m)^\s*client_imported_at=client_imported_at,\s*\r?\n", ''
$main = $main.Replace("client_imported_at=client_imported_at, failed_purchase_at=", "failed_purchase_at=")

if ($main -ne $mainOriginal) {
    Copy-Item $mainPath "$mainPath.8h2-rollback-backup" -Force
    Set-Content $mainPath $main -Encoding UTF8
    Write-Host 'main.py upload-endpoints hersteld.' -ForegroundColor Green
} else {
    Write-Host 'main.py bevatte geen client_imported_at wijzigingen meer.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Rollback uitgevoerd. Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna ZIP-import opnieuw testen. Datumfallback blijft backenddatum zonder tijdstip.' -ForegroundColor Yellow
