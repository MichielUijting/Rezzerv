CLS
$ErrorActionPreference = "Stop"

$Branch = "feature/uitpakken-dagartikelen-release-b"
$Repo = "C:\Users\Gebruiker\Rezzerv_Github"

Set-Location $Repo

Write-Host ""
Write-Host "============================================================"
Write-Host " B4 FINANCIELE AANKOOP ZONDER DIRECTE VOORRAAD"
Write-Host "============================================================"

if (git status --porcelain) {
    git status --short
    throw "STOP: er staan lokale wijzigingen."
}

git fetch origin
if ($LASTEXITCODE -ne 0) { throw "Git fetch is mislukt." }

git switch $Branch
if ($LASTEXITCODE -ne 0) { throw "Branch wisselen is mislukt." }

git pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) { throw "Git pull is mislukt." }

python .\scripts\fix_b4_financial_purchase_without_direct_inventory.py
if ($LASTEXITCODE -ne 0) { throw "De B4-financiele reparatie kon niet worden toegepast." }

python -m compileall `
    backend\app\services\day_article_service.py `
    backend\app\services\day_article_batch_processing_service.py `
    backend\app\main.py
if ($LASTEXITCODE -ne 0) { throw "Python-syntaxcontrole is mislukt." }

docker compose build backend
if ($LASTEXITCODE -ne 0) { throw "De backend-Dockerbuild is mislukt." }

docker compose run --rm --no-deps backend `
    sh -lc "pip install --no-cache-dir pytest==8.3.5 && python -m pytest -q tests/test_day_article_release_b4_batch_processing_contract.py tests/test_day_article_release_b_defaults.py tests/test_day_article_release_b3_line_override_contract.py tests/test_day_article_release_b_direct_location_contract.py"
if ($LASTEXITCODE -ne 0) { throw "De B4- en regressietests zijn mislukt." }

Remove-Item .\scripts\apply_b4_financial_purchase_without_direct_inventory.ps1 -Force
Remove-Item .\scripts\fix_b4_financial_purchase_without_direct_inventory.py -Force

git add -A
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "Git heeft ongeldige wijzigingen gevonden." }

git commit -m "fix(day-articles): register direct purchases financially without stock"
if ($LASTEXITCODE -ne 0) { throw "De definitieve B4-reparatiecommit kon niet worden gemaakt." }

git push origin $Branch
if ($LASTEXITCODE -ne 0) { throw "De B4-reparatie kon niet naar GitHub worden gestuurd." }

$Commit = git rev-parse --short HEAD
Write-Host ""
Write-Host "============================================================"
Write-Host " B4 FINANCIELE REPARATIE IS GEPUSHT"
Write-Host " Branch : $Branch"
Write-Host " Commit : $Commit"
Write-Host "============================================================"
