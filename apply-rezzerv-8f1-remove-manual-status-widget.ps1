$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8F-1 legacy manual status widget verwijderen...' -ForegroundColor Cyan

$path = Join-Path $root 'frontend/src/features/receipts/KassaPage.jsx'
if (-not (Test-Path $path)) {
    throw "Bestand niet gevonden: $path"
}

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

# 1. In de samenvatting mag Handmatig niet meer als aparte key bestaan.
$content = $content -replace "(?m)^\s*Handmatig:\s*inboxItems\.filter\(\(item\) => item\.inbox_status === 'Handmatig'\)\.length,\r?\n", ''
$content = $content -replace "(?m)^\s*'Handmatig':\s*inboxItems\.filter\(\(item\) => item\.inbox_status === 'Handmatig'\)\.length,\r?\n", ''

# 2. De oude statuskaart volledig verwijderen uit de cards-array.
$content = $content -replace "(?m)^\s*\{ key: 'Handmatig', helper: 'Handmatige beoordeling nodig' \},\r?\n", ''
$content = $content -replace "(?m)^\s*\{ key: 'Controle nodig', helper: 'Handmatige beoordeling nodig' \},\r?\n", ''
$content = $content -replace "(?m)^\s*\{ key: 'Controle nodig', helper: 'Controle nodige beoordeling nodig' \},\r?\n", ''

# 3. Indien er twee identieke Controle nodig cards zijn ontstaan, laat alleen de correcte helperregel staan.
$duplicateCard = "                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },`r`n                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },"
$content = $content.Replace($duplicateCard, "                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },")
$duplicateCardLf = "                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },`n                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },"
$content = $content.Replace($duplicateCardLf, "                  { key: 'Controle nodig', helper: 'Vraagt extra aandacht' },")

# 4. Maak box-shadow fallback ook tweestatus: alles wat niet Gecontroleerd is, krijgt Controle nodig accent.
$content = $content.Replace("entry.key === 'Gecontroleerd' ? 'rgba(18,183,106,0.12)' : entry.key === 'Controle nodig' ? 'rgba(247,144,9,0.12)' : 'rgba(181,71,8,0.12)'", "entry.key === 'Gecontroleerd' ? 'rgba(18,183,106,0.12)' : 'rgba(247,144,9,0.12)'")
$content = $content.Replace("item.inbox_status === 'Gecontroleerd' ? '#12B76A' : item.inbox_status === 'Controle nodig' ? '#F79009' : '#B54708'", "item.inbox_status === 'Gecontroleerd' ? '#12B76A' : '#F79009'")

if ($content -ne $original) {
    Copy-Item $path "$path.8f1-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Legacy manual status widget verwijderd uit KassaPage.jsx' -ForegroundColor Green
} else {
    Write-Host 'Geen legacy manual status widget gevonden; mogelijk al opgeschoond.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
