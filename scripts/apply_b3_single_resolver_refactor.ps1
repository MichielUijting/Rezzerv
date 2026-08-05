$ErrorActionPreference = 'Stop'

$ProjectMap = 'C:\Users\Gebruiker\Rezzerv_Github'
$Branch = 'feature/uitpakken-dagartikelen-release-b'
Set-Location $ProjectMap

if (git status --porcelain) {
    git status --short
    throw 'STOP: er staan lokale wijzigingen.'
}

git switch $Branch
if ($LASTEXITCODE -ne 0) { throw 'Wisselen naar de B3-branch is mislukt.' }

git pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'De nieuwste B3-code kon niet worden opgehaald.' }

python .\scripts\refactor_b3_single_handling_resolver.py
if ($LASTEXITCODE -ne 0) { throw 'De centrale B3-refactor is mislukt.' }

$Shared = Get-Content '.\frontend\src\features\stores\storeImportShared.jsx' -Raw
$Page = Get-Content '.\frontend\src\features\stores\StoreBatchDetailPage.jsx' -Raw
$Handling = Get-Content '.\frontend\src\features\receipts\dayArticleHandling.js' -Raw

if ($Shared.Contains('addDayArticlePresentation')) { throw 'STOP: oude addDayArticlePresentation-code is niet verwijderd.' }
if ($Shared.Contains('isPurchaseImportBatchRequest')) { throw 'STOP: oude batchonderschepping is niet verwijderd.' }
if (-not $Handling.Contains('resolveEffectiveLineDestination')) { throw 'STOP: centrale resolver ontbreekt.' }
if (-not $Page.Contains('handlingReconcileRef')) { throw 'STOP: centrale reconciliatie ontbreekt in Uitpakken.' }
if (Test-Path '.\frontend\src\features\receipts\InventoryHandlingOverrideSelect.jsx') { throw 'STOP: oude losse selector bestaat nog.' }

Push-Location frontend
npm run build
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    throw 'De frontendbuild is mislukt.'
}
Pop-Location

Remove-Item '.\scripts\refactor_b3_single_handling_resolver.py' -Force
Remove-Item '.\scripts\apply_b3_single_resolver_refactor.ps1' -Force

git add -A
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Git heeft ongeldige wijzigingen gevonden.' }

git commit -m 'refactor(day-articles): centralize effective handling resolution'
if ($LASTEXITCODE -ne 0) { throw 'De centrale B3-refactor kon niet worden gecommit.' }

git push origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'De centrale B3-refactor kon niet worden gepusht.' }

$Commit = git rev-parse --short HEAD
Write-Host ''
Write-Host '============================================================'
Write-Host ' B3 CENTRALE RESOLVER IS GEPUSHT'
Write-Host " Commit : $Commit"
Write-Host '============================================================'
