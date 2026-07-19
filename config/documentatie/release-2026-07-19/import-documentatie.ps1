[CmdletBinding()]
param(
    [string]$ArchivePath = (Join-Path $env:USERPROFILE 'Downloads\Rezzerv-documentatie_bijgewerkt_2026-07-19.zip')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$target = Join-Path $repoRoot 'config\documentatie\release-2026-07-19'

Write-Host '[1/6] Controleer documentatiearchief'
if (-not (Test-Path -LiteralPath $ArchivePath)) {
    throw "Documentatiearchief ontbreekt: $ArchivePath"
}

Write-Host '[2/6] Maak configuratiemap gereed'
New-Item -ItemType Directory -Force -Path $target | Out-Null

Write-Host '[3/6] Kopieer origineel ZIP-archief'
$archiveTarget = Join-Path $target 'Rezzerv-documentatie_bijgewerkt_2026-07-19.zip'
Copy-Item -LiteralPath $ArchivePath -Destination $archiveTarget -Force

Write-Host '[4/6] Pak originele documentbestanden uit'
Expand-Archive -LiteralPath $ArchivePath -DestinationPath $target -Force

Write-Host '[5/6] Voeg documentatie toe aan Git'
Set-Location $repoRoot
git add -- 'config/documentatie/release-2026-07-19'
if ($LASTEXITCODE -ne 0) { throw 'git add is mislukt.' }

git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check is mislukt.' }

Write-Host '[6/6] Toon klaarstaande Git-wijzigingen'
git status --short -- 'config/documentatie/release-2026-07-19'

Write-Host ''
Write-Host 'DOCUMENTATIE STAAT IN DE REZZERV-CONFIGURATIEMAP EN IS KLAAR VOOR COMMIT.'
Write-Host 'De bestanden zijn nog niet automatisch gepusht; controleer eerst de getoonde lijst.'
