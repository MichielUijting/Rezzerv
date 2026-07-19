[CmdletBinding()]
param(
    [string]$ArchivePath = (Join-Path $env:USERPROFILE 'Downloads\Rezzerv-documentatie_bijgewerkt_2026-07-19.zip')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$target = Join-Path $repoRoot 'config\documentatie\release-2026-07-19'

Write-Host '[1/8] Controleer documentatiearchief'
if (-not (Test-Path -LiteralPath $ArchivePath)) {
    throw "Documentatiearchief ontbreekt: $ArchivePath"
}

Write-Host '[2/8] Controleer actuele Git-branch'
Set-Location $repoRoot
$branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
    throw 'Actuele Git-branch kon niet worden vastgesteld.'
}

Write-Host '[3/8] Maak configuratiemap gereed'
New-Item -ItemType Directory -Force -Path $target | Out-Null

Write-Host '[4/8] Kopieer origineel ZIP-archief'
$archiveTarget = Join-Path $target 'Rezzerv-documentatie_bijgewerkt_2026-07-19.zip'
Copy-Item -LiteralPath $ArchivePath -Destination $archiveTarget -Force

Write-Host '[5/8] Pak originele documentbestanden uit'
Expand-Archive -LiteralPath $ArchivePath -DestinationPath $target -Force

Write-Host '[6/8] Voeg documentatie toe aan Git'
git add -- 'config/documentatie/release-2026-07-19'
if ($LASTEXITCODE -ne 0) { throw 'git add is mislukt.' }

git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check is mislukt.' }

$changes = git diff --cached --name-only -- 'config/documentatie/release-2026-07-19'
if (-not $changes) {
    Write-Host 'De documentatie staat al volledig en ongewijzigd in Git.'
    exit 0
}

Write-Host '[7/8] Commit documentatieset'
git commit -m 'Voeg bijgewerkte Rezzerv-documentatieset toe'
if ($LASTEXITCODE -ne 0) { throw 'git commit is mislukt.' }

Write-Host '[8/8] Push documentatie naar GitHub'
git push origin $branch
if ($LASTEXITCODE -ne 0) { throw 'git push is mislukt.' }

Write-Host ''
Write-Host '============================================================'
Write-Host ' DOCUMENTATIE OPGESLAGEN IN GIT EN GEPUSHT'
Write-Host " Branch: $branch"
Write-Host ' Map: config/documentatie/release-2026-07-19'
Write-Host '============================================================'
Write-Host ''
