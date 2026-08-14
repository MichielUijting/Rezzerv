CLS
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$ExpectedBranch = 'fix/uitpakken-admin-location-create'
$runFailed = $false

try {
    Write-Host '==================================================' -ForegroundColor Cyan
    Write-Host ' UITPAKKEN ADMIN LOCATIE TOEVOEGEN - PRE-MERGE' -ForegroundColor Cyan
    Write-Host '==================================================' -ForegroundColor Cyan

    Write-Host ''
    Write-Host '[1/5] Branch en werkmap controleren' -ForegroundColor Cyan
    $branch = (git branch --show-current).Trim()
    if ($branch -ne $ExpectedBranch) {
        throw "Verkeerde branch: $branch. Verwacht: $ExpectedBranch"
    }
    if (git status --porcelain) {
        git status --short
        throw 'Werkmap is niet schoon.'
    }
    git fetch origin
    if ($LASTEXITCODE -ne 0) { throw 'git fetch mislukt.' }
    $head = (git rev-parse HEAD).Trim()
    $remoteHead = (git rev-parse "origin/$ExpectedBranch").Trim()
    if ($head -ne $remoteHead) {
        throw "Lokale head $head is niet gelijk aan GitHub-head $remoteHead. Voer eerst git pull --ff-only uit."
    }
    Write-Host "[PASS] branch/head: $head" -ForegroundColor Green

    Write-Host ''
    Write-Host '[2/5] Gerichte Admin-locatie contracttests' -ForegroundColor Cyan
    $rootForDocker = $repoRoot.Replace('\', '/')
    docker compose run --rm --no-deps `
        -e PYTHONPATH=/app `
        -v "${rootForDocker}/backend:/backend:ro" `
        -v "${rootForDocker}/frontend:/frontend:ro" `
        backend sh -lc "python -m pip install --disable-pip-version-check -q pytest && python -m pytest -q /backend/tests/test_uitpakken_location_admin_contract.py"
    if ($LASTEXITCODE -ne 0) { throw "Gerichte Admin-locatie contracttests zijn rood met exitcode $LASTEXITCODE." }
    Write-Host '[PASS] gerichte contracttests groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '[3/5] Volledige centrale frontendregressie' -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'run-frontend-regression-report.ps1')
    if ($LASTEXITCODE -ne 0) { throw "Centrale frontendregressie is rood met exitcode $LASTEXITCODE." }
    Write-Host '[PASS] volledige frontendregressie groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '[4/5] Receipt -> Voorraad -> Bijna-op ketentest V2' -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'run-receipt-inventory-chain-v2.ps1') -SkipBackendBuild
    if ($LASTEXITCODE -ne 0) { throw "Receipt-inventory ketentest is rood met exitcode $LASTEXITCODE." }
    Write-Host '[PASS] receipt-inventory ketentest groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '[5/5] Diff- en fixturehygiene' -ForegroundColor Cyan
    git fetch origin main
    if ($LASTEXITCODE -ne 0) { throw 'Actuele main kon niet worden opgehaald.' }
    git diff --check origin/main...HEAD
    if ($LASTEXITCODE -ne 0) { throw 'git diff --check tegen main is rood.' }
    if (git status --porcelain) {
        git status --short
        throw 'De testfase heeft lokale repositorywijzigingen achtergelaten.'
    }

    Write-Host ''
    Write-Host '==================================================' -ForegroundColor Green
    Write-Host ' PR #242 PRE-MERGE REGRESSIE + KETEN VOLLEDIG GROEN' -ForegroundColor Green
    Write-Host '==================================================' -ForegroundColor Green
    Write-Host "Geteste commit       : $head"
    Write-Host 'Admin-locatie contract: GREEN'
    Write-Host 'Frontendregressie     : GREEN'
    Write-Host 'Receipt-inventory     : GREEN'
    Write-Host 'Werkmap/fixtures      : CLEAN'
    exit 0
}
catch {
    $runFailed = $true
    Write-Host ''
    Write-Host '==================================================' -ForegroundColor Red
    Write-Host ' PR #242 PRE-MERGE TESTSET ROOD - STOP' -ForegroundColor Red
    Write-Host '==================================================' -ForegroundColor Red
    Write-Host ("Oorzaak: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
