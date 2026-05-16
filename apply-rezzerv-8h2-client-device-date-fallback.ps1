$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8H-2 client device date fallback starten...' -ForegroundColor Cyan

$frontendPath = Join-Path $root 'frontend/src/features/receipts/KassaPage.jsx'
$backendPath = Join-Path $root 'backend/app/services/receipt_service.py'
$mainPath = Join-Path $root 'backend/app/main.py'

foreach ($path in @($frontendPath, $backendPath, $mainPath)) {
    if (-not (Test-Path $path)) { throw "Bestand niet gevonden: $path" }
}

# 1. Frontend: stuur apparaatdatum/tijd mee met alle uploadvormen.
$frontend = Get-Content $frontendPath -Raw -Encoding UTF8
$frontendOriginal = $frontend

if ($frontend -notmatch 'function getClientImportedAt') {
$helper = @'

function getClientImportedAt() {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
}
'@
    $anchor = 'function loadStoredReceiptIds(storageKey) {'
    if (-not $frontend.Contains($anchor)) { throw 'Frontend anchor loadStoredReceiptIds niet gevonden.' }
    $frontend = $frontend.Replace($anchor, ($helper + "`r`n" + $anchor))
}

$frontend = $frontend.Replace("  formData.append('file', file)`r`n", "  formData.append('file', file)`r`n  formData.append('client_imported_at', getClientImportedAt())`r`n")
$frontend = $frontend.Replace("  formData.append('file', file)`n", "  formData.append('file', file)`n  formData.append('client_imported_at', getClientImportedAt())`n")
$frontend = $frontend.Replace("  formData.append('email_file', emailFile)`r`n", "  formData.append('email_file', emailFile)`r`n  formData.append('client_imported_at', getClientImportedAt())`r`n")
$frontend = $frontend.Replace("  formData.append('email_file', emailFile)`n", "  formData.append('email_file', emailFile)`n  formData.append('client_imported_at', getClientImportedAt())`n")

if ($frontend -ne $frontendOriginal) {
    Copy-Item $frontendPath "$frontendPath.8h2-client-date-backup" -Force
    Set-Content $frontendPath $frontend -Encoding UTF8
    Write-Host 'Frontend stuurt client_imported_at mee.' -ForegroundColor Green
} else {
    Write-Host 'Frontend leek al client_imported_at te sturen.' -ForegroundColor Yellow
}

# 2. Backend service: accepteer client_imported_at als fallback boven backenddatum.
$backend = Get-Content $backendPath -Raw -Encoding UTF8
$backendOriginal = $backend

$backend = $backend.Replace(
    "def _purchase_at_or_system_date(value: str | None) -> str:",
    "def _purchase_at_or_system_date(value: str | None, client_imported_at: str | None = None) -> str:"
)
$backend = $backend.Replace(
    "    parsed = str(value or '').strip()`r`n    if parsed:`r`n        return parsed`r`n    return datetime.utcnow().date().isoformat()",
    "    parsed = str(value or '').strip()`r`n    if parsed:`r`n        return parsed`r`n    client_value = str(client_imported_at or '').strip()`r`n    if client_value:`r`n        return client_value`r`n    return datetime.utcnow().astimezone().replace(microsecond=0).isoformat()"
)
$backend = $backend.Replace(
    "def ingest_receipt(engine, receipt_storage_root: Path, household_id: str, filename: str, file_bytes: bytes, source_id: str | None = None, mime_type: str | None = None, reject_non_receipt: bool = False, create_failed_receipt_table: bool = False, failed_store_name: str | None = None, failed_purchase_at: str | None = None) -> dict[str, Any]:",
    "def ingest_receipt(engine, receipt_storage_root: Path, household_id: str, filename: str, file_bytes: bytes, source_id: str | None = None, mime_type: str | None = None, reject_non_receipt: bool = False, create_failed_receipt_table: bool = False, failed_store_name: str | None = None, failed_purchase_at: str | None = None, client_imported_at: str | None = None) -> dict[str, Any]:"
)
$backend = $backend.Replace(
    "            table_purchase_at = _purchase_at_or_system_date(parse_result.purchase_at if parse_result.is_receipt else failed_purchase_at)",
    "            table_purchase_at = _purchase_at_or_system_date(parse_result.purchase_at if parse_result.is_receipt else failed_purchase_at, client_imported_at)"
)

if ($backend -ne $backendOriginal) {
    Copy-Item $backendPath "$backendPath.8h2-client-date-backup" -Force
    Set-Content $backendPath $backend -Encoding UTF8
    Write-Host 'Backend service gebruikt client_imported_at als datumfallback.' -ForegroundColor Green
} else {
    Write-Host 'Backend service leek al aangepast of wijkt af.' -ForegroundColor Yellow
}

# 3. main.py: Form-parameter opnemen en doorgeven aan ingest_receipt.
$main = Get-Content $mainPath -Raw -Encoding UTF8
$mainOriginal = $main

# Voeg client_imported_at form parameter toe bij upload endpoints waar household_id als Form voorkomt.
$main = $main.Replace("household_id: str = Form(...),`r`n    file: UploadFile = File(...),", "household_id: str = Form(...),`r`n    file: UploadFile = File(...),`r`n    client_imported_at: str | None = Form(None),")
$main = $main.Replace("household_id: str = Form(...),`n    file: UploadFile = File(...),", "household_id: str = Form(...),`n    file: UploadFile = File(...),`n    client_imported_at: str | None = Form(None),")
$main = $main.Replace("household_id: str = Form(...),`r`n    email_file: UploadFile = File(...),", "household_id: str = Form(...),`r`n    email_file: UploadFile = File(...),`r`n    client_imported_at: str | None = Form(None),")
$main = $main.Replace("household_id: str = Form(...),`n    email_file: UploadFile = File(...),", "household_id: str = Form(...),`n    email_file: UploadFile = File(...),`n    client_imported_at: str | None = Form(None),")

# Geef parameter door aan ingest_receipt waar aanwezig. Dit is idempotent gemaakt.
$main = $main.Replace("failed_purchase_at=", "client_imported_at=client_imported_at, failed_purchase_at=")
$main = $main.Replace("reject_non_receipt=True,`r`n        )", "reject_non_receipt=True,`r`n            client_imported_at=client_imported_at,`r`n        )")
$main = $main.Replace("reject_non_receipt=True,`n        )", "reject_non_receipt=True,`n            client_imported_at=client_imported_at,`n        )")
$main = $main.Replace("source_id=source_id,`r`n        )", "source_id=source_id,`r`n            client_imported_at=client_imported_at,`r`n        )")
$main = $main.Replace("source_id=source_id,`n        )", "source_id=source_id,`n            client_imported_at=client_imported_at,`n        )")

if ($main -ne $mainOriginal) {
    Copy-Item $mainPath "$mainPath.8h2-client-date-backup" -Force
    Set-Content $mainPath $main -Encoding UTF8
    Write-Host 'main.py geeft client_imported_at door aan ingest_receipt.' -ForegroundColor Green
} else {
    Write-Host 'main.py leek al aangepast of patronen zijn niet gevonden.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host '8H-2 client device date fallback toegepast.' -ForegroundColor Green
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna bonnen opnieuw importeren. Fallbackdatum komt nu van het apparaat/browser.' -ForegroundColor Yellow
