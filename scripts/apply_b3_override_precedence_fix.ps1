$ErrorActionPreference = 'Stop'

$Branch = 'feature/uitpakken-dagartikelen-release-b'
$ProjectMap = 'C:\Users\Gebruiker\Rezzerv_Github'

Set-Location $ProjectMap

if (git status --porcelain) {
    git status --short
    throw 'STOP: er staan lokale wijzigingen.'
}

git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'git fetch is mislukt.' }

git switch $Branch
if ($LASTEXITCODE -ne 0) { throw 'Wisselen naar de featurebranch is mislukt.' }

git pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'git pull is mislukt.' }

python .\scripts\fix_b3_override_precedence.py
if ($LASTEXITCODE -ne 0) { throw 'De bronreparatie is mislukt.' }

Push-Location frontend
npm run build
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    throw 'De frontendbuild is mislukt.'
}
Pop-Location

$Shared = Get-Content 'frontend\src\features\stores\storeImportShared.jsx' -Raw
if (-not $Shared.Contains('/purchase-import-lines/inventory-handling-overrides/batch')) {
    throw 'De regelafwijkingen worden nog niet geladen.'
}
if (-not $Shared.Contains('const effectiveHandling = lineOverride || articleDefault')) {
    throw 'De B3-voorrangsregel ontbreekt.'
}

Remove-Item '.\scripts\fix_b3_override_precedence.py' -Force
Remove-Item '.\scripts\apply_b3_override_precedence_fix.ps1' -Force

git add -A
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Git heeft ongeldige wijzigingen gevonden.' }

git commit -m 'fix(day-articles): honor line override before article default'
if ($LASTEXITCODE -ne 0) { throw 'De commit kon niet worden gemaakt.' }

git push origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'De commit kon niet worden gepusht.' }

$Commit = git rev-parse --short HEAD
Write-Host ''
Write-Host '============================================================'
Write-Host ' B3 VOORRANGSREPARATIE IS GEPUSHT'
Write-Host " Commit : $Commit"
Write-Host '============================================================'
