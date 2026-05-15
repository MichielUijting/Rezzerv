$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8F KassaPage build-hotfix starten...' -ForegroundColor Cyan

$path = Join-Path $root 'frontend/src/features/receipts/KassaPage.jsx'
if (-not (Test-Path $path)) {
    throw "Bestand niet gevonden: $path"
}

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

$brokenLine = "      Controle nodig: inboxItems.filter((item) => item.inbox_status === 'Controle nodig').length,`r`n"
$content = $content.Replace($brokenLine, '')

$brokenLineLf = "      Controle nodig: inboxItems.filter((item) => item.inbox_status === 'Controle nodig').length,`n"
$content = $content.Replace($brokenLineLf, '')

if ($content -ne $original) {
    Copy-Item $path "$path.8f-build-hotfix-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Foutieve dubbele object-key verwijderd uit KassaPage.jsx' -ForegroundColor Green
} else {
    Write-Host 'Geen foutieve object-key gevonden; mogelijk al hersteld.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
