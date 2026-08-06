CLS
$ErrorActionPreference = "Stop"

$Branch = "feature/uitpakken-dagartikelen-release-b"
$Repo = "C:\Users\Gebruiker\Rezzerv_Github"
Set-Location $Repo

if (git status --porcelain) {
    git status --short
    throw "STOP: er staan lokale wijzigingen."
}

git switch $Branch
if ($LASTEXITCODE -ne 0) { throw "Branch wisselen is mislukt." }

git pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) { throw "Git pull is mislukt." }

python .\scripts\refactor_household_article_identity_slice1.py
if ($LASTEXITCODE -ne 0) { throw "De eerste Huishoudartikel-refactorslice kon niet worden toegepast." }

Push-Location frontend
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontendbuild is mislukt." }

    npx vitest run `
        src/features/stores/householdArticleIdentity.single-source.contract.test.js `
        src/features/stores/householdArticleOptionAdapter.test.js `
        src/features/stores/StoreBatchDetailPage.b3-native.contract.test.js
    if ($LASTEXITCODE -ne 0) { throw "Gerichte frontendtests zijn mislukt." }
}
finally {
    Pop-Location
}

Remove-Item .\scripts\apply_household_article_identity_slice1.ps1 -Force
Remove-Item .\scripts\refactor_household_article_identity_slice1.py -Force

git add -A
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "Git heeft ongeldige wijzigingen gevonden." }

git commit -m "refactor(articles): scope identity normalization to unpacking"
if ($LASTEXITCODE -ne 0) { throw "De refactorcommit kon niet worden gemaakt." }

git push origin $Branch
if ($LASTEXITCODE -ne 0) { throw "De refactorcommit kon niet worden gepusht." }

$Commit = git rev-parse --short HEAD
Write-Host ""
Write-Host "============================================================"
Write-Host " HUISHOUDARTIKEL IDENTITEIT SLICE 1 IS GEPUSHT"
Write-Host " Branch : $Branch"
Write-Host " Commit : $Commit"
Write-Host "============================================================"
