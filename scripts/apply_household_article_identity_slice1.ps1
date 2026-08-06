CLS
$ErrorActionPreference = "Stop"

$Branch = "feature/uitpakken-dagartikelen-release-b"
$Repo = "C:\Users\Gebruiker\Rezzerv_Github"
Set-Location $Repo

Write-Host "============================================================"
Write-Host " HUISHOUDARTIKEL IDENTITEIT SLICE 1"
Write-Host "============================================================"

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

Write-Host ""
Write-Host "[1/4] Docker-runtime volledig opnieuw opbouwen"
docker compose down
if ($LASTEXITCODE -ne 0) { throw "Docker Compose kon niet worden gestopt." }

docker compose up -d --build --force-recreate --remove-orphans
if ($LASTEXITCODE -ne 0) { throw "Docker Compose build/start is mislukt." }

Write-Host ""
Write-Host "[2/4] Backend-health controleren"
$HealthOk = $false
for ($Poging = 1; $Poging -le 18; $Poging++) {
    try {
        $Health = Invoke-RestMethod -Uri "http://localhost:8011/api/health" -Method Get -TimeoutSec 15
        $HealthOk = $true
        break
    }
    catch {
        Start-Sleep -Seconds 10
    }
}
if (-not $HealthOk) { throw "Backend-health bleef onbereikbaar." }
$Health | Format-List

Write-Host ""
Write-Host "[3/4] Officiele frontend-regressie uitvoeren"
& .\scripts\run-frontend-regression-report.ps1 -SkipDockerBuild
if ($LASTEXITCODE -ne 0) { throw "De officiele frontend-regressie is mislukt." }

Write-Host ""
Write-Host "[4/4] Kassabon-voorraadketen uitvoeren"
& .\scripts\run-receipt-inventory-chain.ps1
if ($LASTEXITCODE -ne 0) { throw "De kassabon-voorraadketen is mislukt." }

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
