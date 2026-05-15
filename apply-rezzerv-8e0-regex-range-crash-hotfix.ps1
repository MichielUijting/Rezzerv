$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8E-0 ASCII-safe regex crash hotfix starten...' -ForegroundColor Cyan

$targets = @(
    'backend/app/services/receipt_service.py',
    'backend/app/api/receipt_import_diagnosis_routes.py'
)

# Gebruik byte sequences i.p.v. speciale tekens, zodat PowerShell niet struikelt over encoding.
$utf8 = [System.Text.Encoding]::UTF8
$pairs = @(
    @([byte[]](0xE2,0x82,0xAC,0x2D,0xC3,0x83), [byte[]](0xE2,0x82,0xAC,0xC3,0x83)),
    @([byte[]](0xC3,0x83,0x2D,0xE2,0x82,0xAC), [byte[]](0xC3,0x83,0xE2,0x82,0xAC)),
    @([byte[]](0xE2,0x82,0xAC,0x2D,0xC3,0x82), [byte[]](0xE2,0x82,0xAC,0xC3,0x82)),
    @([byte[]](0xC3,0x82,0x2D,0xE2,0x82,0xAC), [byte[]](0xC3,0x82,0xE2,0x82,0xAC))
)

$changed = $false
foreach ($relativePath in $targets) {
    $path = Join-Path $root $relativePath
    if (-not (Test-Path $path)) { continue }

    $content = Get-Content $path -Raw -Encoding UTF8
    $original = $content

    foreach ($pair in $pairs) {
        $from = $utf8.GetString($pair[0])
        $to = $utf8.GetString($pair[1])
        $content = $content.Replace($from, $to)
    }

    if ($content -ne $original) {
        Copy-Item $path "$path.regex-hotfix-backup" -Force
        Set-Content $path $content -Encoding UTF8
        Write-Host "Aangepast: $relativePath" -ForegroundColor Green
        $changed = $true
    } else {
        Write-Host "Geen directe crashrange gevonden in: $relativePath" -ForegroundColor DarkGray
    }
}

# Compile-check: importeer receipt_service en dwing Python regex-compilatie via de diagnose-route straks in Docker.
Write-Host ''
if ($changed) {
    Write-Host 'Regex range crash hotfix toegepast.' -ForegroundColor Green
} else {
    Write-Host 'Geen tekstuele crashrange gevonden. Als de fout blijft bestaan, zit hij in dynamisch opgebouwde regex.' -ForegroundColor Yellow
}

Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna opnieuw POST /api/receipt-import-diagnosis/zip-dry-run testen met supermarkten.zip.' -ForegroundColor Yellow
