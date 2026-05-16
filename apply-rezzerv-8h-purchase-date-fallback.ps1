$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8H aankoopdatum fallback starten...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/services/receipt_service.py'
if (-not (Test-Path $path)) {
    throw "Bestand niet gevonden: $path"
}

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

# Voeg helper toe als die nog ontbreekt.
if ($content -notmatch 'def _purchase_at_or_system_date') {
$helper = @'


def _purchase_at_or_system_date(value: str | None) -> str:
    """Return parsed receipt date or current system date as safe import fallback.

    This fallback is only for visibility and workflow continuity in Kassa.
    It does not approve a receipt and does not replace financial validation.
    """
    parsed = str(value or '').strip()
    if parsed:
        return parsed
    return datetime.utcnow().date().isoformat()
'@
    $anchor = "def ingest_receipt("
    if (-not $content.Contains($anchor)) {
        throw 'Kan ingest_receipt anchor niet vinden.'
    }
    $content = $content.Replace($anchor, ($helper + "`r`n`r`n" + $anchor))
}

# Nieuwe imports zijn niet nodig als datetime al in receipt_service.py aanwezig is.
# Vervang de directe purchase_at-overname door fallback bij normale en failed receipt table creation.
$content = $content.Replace(
    "            table_purchase_at = parse_result.purchase_at if parse_result.is_receipt else failed_purchase_at",
    "            table_purchase_at = _purchase_at_or_system_date(parse_result.purchase_at if parse_result.is_receipt else failed_purchase_at)"
)

# Ook bij reparse mag een lege aankoopdatum niet opnieuw naar NULL worden geschreven.
$content = $content.Replace(
    "'purchase_at': parse_result.purchase_at,",
    "'purchase_at': _purchase_at_or_system_date(parse_result.purchase_at),"
)

if ($content -ne $original) {
    Copy-Item $path "$path.8h-date-fallback-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Aankoopdatum fallback toegepast in receipt_service.py' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast; fallback was mogelijk al aanwezig.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna de 14 bonnen opnieuw importeren en controleren of Datum niet meer overal - is.' -ForegroundColor Yellow
