$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$expectedBranch = 'feature/uitpakken-dagartikelen-release-b'
$currentBranch = (git branch --show-current).Trim()
if ($currentBranch -ne $expectedBranch) {
    throw "Verkeerde branch: $currentBranch. Verwacht: $expectedBranch"
}

if (git status --porcelain) {
    git status --short
    throw 'STOP: de werkmap bevat lokale wijzigingen.'
}

Write-Host '[1/6] B3 locatie-ontwerp toepassen'
python scripts/temp_b3_location_only.py
if ($LASTEXITCODE -ne 0) { throw 'De bronwijziging is mislukt.' }

Write-Host '[2/6] Frontend bouwen'
Push-Location frontend
npm ci
if ($LASTEXITCODE -ne 0) { throw 'npm ci is mislukt.' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Frontendbuild is mislukt.' }

Write-Host '[3/6] Gerichte B3-test uitvoeren'
npm test -- --run src/features/stores/StoreBatchDetailPage.b3-native.contract.test.js
if ($LASTEXITCODE -ne 0) { throw 'De gerichte B3-test is mislukt.' }
Pop-Location

Write-Host '[4/6] Tijdelijke ontwikkelbestanden verwijderen'
$temporaryFiles = @(
    '.github/workflows/temp-b3-location-only-integration.yml',
    'scripts/temp_b3_location_only.py',
    'scripts/apply_b3_location_only.ps1'
)
foreach ($file in $temporaryFiles) {
    if (Test-Path $file) { Remove-Item $file -Force }
}

Write-Host '[5/6] Definitieve wijziging committen'
git add -A
git commit -m 'refactor(day-articles): use Locatie as the only B3 control'
if ($LASTEXITCODE -ne 0) { throw 'Git commit is mislukt.' }

Write-Host '[6/6] Naar GitHub pushen'
git push origin HEAD:$expectedBranch
if ($LASTEXITCODE -ne 0) { throw 'Git push is mislukt.' }

Write-Host ''
Write-Host 'B3 locatie-ontwerp is toegepast, getest en gepusht.' -ForegroundColor Green
git rev-parse --short HEAD
