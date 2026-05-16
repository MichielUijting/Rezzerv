$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8H-1 datumweergave zonder tijdstip starten...' -ForegroundColor Cyan

$path = Join-Path $root 'frontend/src/features/receipts/KassaPage.jsx'
if (-not (Test-Path $path)) {
    throw "Bestand niet gevonden: $path"
}

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

$old = @'
function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('nl-NL', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
'@

$new = @'
function formatDateTime(value) {
  if (!value) return '-'
  const textValue = String(value).trim()
  const isoDateMatch = textValue.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (isoDateMatch) return `${isoDateMatch[3]}-${isoDateMatch[2]}-${isoDateMatch[1]}`
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return textValue
  return new Intl.DateTimeFormat('nl-NL', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}
'@

if (-not $content.Contains($old)) {
    throw 'Kon bestaande formatDateTime functie niet exact vinden. Geen wijziging uitgevoerd.'
}

$content = $content.Replace($old, $new)

if ($content -ne $original) {
    Copy-Item $path "$path.8h1-date-only-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Datumweergave aangepast: alleen datum, geen tijdstip.' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
