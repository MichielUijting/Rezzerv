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

python .\scripts\integrate_b4_direct_batch_processing.py
if ($LASTEXITCODE -ne 0) { throw "De B4-integratie kon niet worden toegepast." }

python -m py_compile `
    .\backend\app\main.py `
    .\backend\app\services\day_article_service.py `
    .\backend\app\services\day_article_batch_processing_service.py
if ($LASTEXITCODE -ne 0) { throw "Python syntaxcontrole is mislukt." }

Push-Location backend
try {
    python -m pytest `
        tests\test_day_article_release_b4_batch_processing_contract.py `
        tests\test_day_article_release_b_defaults.py `
        tests\test_day_article_release_b3_line_override_contract.py `
        -q
    if ($LASTEXITCODE -ne 0) { throw "Gerichte B4-backendtests zijn mislukt." }
}
finally {
    Pop-Location
}

docker compose build backend
if ($LASTEXITCODE -ne 0) { throw "De backendcontainer kon niet worden gebouwd." }

Remove-Item .\scripts\apply_b4_direct_batch_processing.ps1 -Force
Remove-Item .\scripts\integrate_b4_direct_batch_processing.py -Force

git add -A
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "Git heeft ongeldige wijzigingen gevonden." }

git commit -m "feat(day-articles): process Direct lines without inventory mutation"
if ($LASTEXITCODE -ne 0) { throw "De B4-commit kon niet worden gemaakt." }

git push origin $Branch
if ($LASTEXITCODE -ne 0) { throw "De B4-commit kon niet worden gepusht." }

$Commit = git rev-parse --short HEAD
Write-Host ""
Write-Host "============================================================"
Write-Host " B4 DIRECTE BATCHVERWERKING IS GEPUSHT"
Write-Host " Commit : $Commit"
Write-Host "============================================================"
