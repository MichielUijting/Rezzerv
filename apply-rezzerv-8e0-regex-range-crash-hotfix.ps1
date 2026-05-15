$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8E-0 regex range crash hotfix starten...' -ForegroundColor Cyan

$targets = @(
    'backend/app/services/receipt_service.py',
    'backend/app/api/receipt_import_diagnosis_routes.py'
)

$changed = $false
foreach ($relativePath in $targets) {
    $path = Join-Path $root $relativePath
    if (-not (Test-Path $path)) {
        continue
    }

    $content = Get-Content $path -Raw
    $original = $content

    # Root-cause fix: Python regex interpreteert €-Ã binnen [] als ongeldige character range.
    # De bedoeling is hier losse tekens toelaten/weghalen, niet een range definiëren.
    $content = $content.Replace('€-Ã', '€Ã')
    $content = $content.Replace('Ã-€', 'Ã€')

    # Extra mojibake-varianten die bij Windows/UTF-8 menging kunnen ontstaan.
    $content = $content.Replace('€-Â', '€Â')
    $content = $content.Replace('Â-€', 'Â€')
    $content = $content.Replace('€-â', '€â')
    $content = $content.Replace('â-€', 'â€')

    if ($content -ne $original) {
        Copy-Item $path "$path.regex-hotfix-backup" -Force
        Set-Content $path $content -Encoding UTF8
        Write-Host "Aangepast: $relativePath" -ForegroundColor Green
        $changed = $true
    } else {
        Write-Host "Geen directe €-Ã range gevonden in: $relativePath" -ForegroundColor DarkGray
    }
}

# Scan daarna alle Pythonbestanden op de specifieke bekende crashrange.
$remaining = Get-ChildItem -Path (Join-Path $root 'backend') -Filter '*.py' -Recurse |
    Select-String -Pattern '€-Ã|Ã-€|€-Â|Â-€|€-â|â-€' -SimpleMatch

if ($remaining) {
    Write-Host ''
    Write-Host 'LET OP: Er zijn nog verdachte regex-ranges gevonden:' -ForegroundColor Red
    $remaining | ForEach-Object { Write-Host ("{0}:{1}: {2}" -f $_.Path, $_.LineNumber, $_.Line.Trim()) -ForegroundColor Red }
    throw 'Regex range crash hotfix niet volledig; verdachte ranges blijven aanwezig.'
}

Write-Host ''
if ($changed) {
    Write-Host 'Regex range crash hotfix toegepast.' -ForegroundColor Green
} else {
    Write-Host 'Geen tekstuele €-Ã range gevonden. Als de fout blijft bestaan, zit hij in dynamisch opgebouwde regex.' -ForegroundColor Yellow
}
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host ''
Write-Host 'Test daarna opnieuw POST /api/receipt-import-diagnosis/zip-dry-run met supermarkten.zip.' -ForegroundColor Yellow
