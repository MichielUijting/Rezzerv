$ErrorActionPreference = "Stop"

$Branch = "feature/uitpakken-dagartikelen-release-b"

if ((git branch --show-current) -ne $Branch) {
    git switch $Branch
}

git pull --ff-only origin $Branch

python .\scripts\fix_b3_atomic_location_choice.py
if ($LASTEXITCODE -ne 0) { throw "De bronreparatie is mislukt." }

Push-Location frontend
npm run build
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    throw "De frontendbuild is mislukt."
}
Pop-Location

$Source = Get-Content .\frontend\src\features\stores\StoreBatchDetailPage.jsx -Raw
if (-not $Source.Contains('async function persistLocationHandlingChoice')) { throw "Centrale opslaghandeling ontbreekt." }
if (-not $Source.Contains('if (overrideSaved)')) { throw "Rollback van de override ontbreekt." }
if (-not $Source.Contains('previousLocationId')) { throw "Rollback van de locatie ontbreekt." }
if ($Source.Contains('const savedOverride = await saveInventoryHandlingOverride(householdId, lineId, isDirect ? DIRECT_CONSUMPTION : STOCK)')) { throw "Oude losse opslaglogica is nog aanwezig." }

git rm .\scripts\apply_b3_atomic_location_choice_fix.ps1
git rm .\scripts\fix_b3_atomic_location_choice.py

git add -A
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "Git vond ongeldige wijzigingen." }

git commit -m "fix(day-articles): save location choice with rollback"
if ($LASTEXITCODE -ne 0) { throw "Commit maken is mislukt." }

git push origin $Branch
if ($LASTEXITCODE -ne 0) { throw "Push naar GitHub is mislukt." }

$Commit = git rev-parse --short HEAD
Write-Host ""
Write-Host "============================================================"
Write-Host " B3 ATOMAIRE LOCATIEKEUZE IS GEPUSHT"
Write-Host " Commit : $Commit"
Write-Host "============================================================"
