CLS
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$Branch = 'feature/receipt-lifecycle-release-b'
$runFailed = $false

try {
    Write-Host '==================================================' -ForegroundColor Cyan
    Write-Host ' REZZERV RELEASE B - PRE-MERGE REGRESSIE + KETEN' -ForegroundColor Cyan
    Write-Host '==================================================' -ForegroundColor Cyan

    Write-Host ''
    Write-Host '[1/6] Git-versie en schone werkmap controleren' -ForegroundColor Cyan
    git fetch origin
    if ($LASTEXITCODE -ne 0) { throw 'git fetch mislukt.' }

    $currentBranch = (git branch --show-current).Trim()
    if ($currentBranch -ne $Branch) {
        throw "Verkeerde branch: $currentBranch. Verwacht: $Branch"
    }

    git pull --ff-only origin $Branch
    if ($LASTEXITCODE -ne 0) { throw 'Branch kon niet fast-forward worden bijgewerkt.' }

    if (git status --porcelain) {
        git status --short
        throw 'Werkmap is niet schoon.'
    }

    $head = (git rev-parse HEAD).Trim()
    $remoteHead = (git rev-parse "origin/$Branch").Trim()
    if ($head -ne $remoteHead) {
        throw "Lokale head $head wijkt af van GitHub-head $remoteHead."
    }
    Write-Host "[PASS] Release-B head: $head" -ForegroundColor Green

    Write-Host ''
    Write-Host '[2/6] Centrale frontendregressie uitvoeren' -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'run-frontend-regression-report.ps1')
    if ($LASTEXITCODE -ne 0) {
        throw "Centrale frontendregressie is rood met exitcode $LASTEXITCODE."
    }
    Write-Host '[PASS] centrale frontendregressie groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '[3/6] Receipt -> Voorraad -> Bijna-op ketentest V2' -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'run-receipt-inventory-chain-v2.ps1') -SkipBackendBuild
    if ($LASTEXITCODE -ne 0) {
        throw "Receipt-inventory ketentest V2 is rood met exitcode $LASTEXITCODE."
    }
    Write-Host '[PASS] receipt-inventory keten groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '[4/6] Release-B gerichte backend regressietests' -ForegroundColor Cyan
    docker compose run --rm --no-deps `
        -e PYTHONPATH=/app `
        backend sh -lc "python -m pip install --disable-pip-version-check -q pytest && python -m pytest -q tests/test_receipt_lifecycle_foundation.py tests/test_receipt_reimport_lineage_service.py tests/test_receipt_lifecycle_release_b_chain.py tests/test_unpacking_readiness_article_model_contract.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Release-B backend regressietests zijn rood met exitcode $LASTEXITCODE."
    }
    Write-Host '[PASS] Release-B backend regressietests groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '[5/6] Diff- en werkmaphygiëne controleren' -ForegroundColor Cyan
    git fetch origin main
    if ($LASTEXITCODE -ne 0) { throw 'Actuele main kon niet worden opgehaald.' }

    git diff --check origin/main...HEAD
    if ($LASTEXITCODE -ne 0) { throw 'git diff --check tegen main is rood.' }

    if (git status --porcelain) {
        git status --short
        throw 'Testfase heeft lokale repositorywijzigingen achtergelaten.'
    }
    Write-Host '[PASS] geen diff- of fixturevervuiling' -ForegroundColor Green

    Write-Host ''
    Write-Host '[6/6] Eindstatus' -ForegroundColor Cyan
    Write-Host '==================================================' -ForegroundColor Green
    Write-Host ' RELEASE B PRE-MERGE TESTSET VOLLEDIG GROEN' -ForegroundColor Green
    Write-Host '==================================================' -ForegroundColor Green
    Write-Host "Geteste commit: $head"
    Write-Host 'Frontendregressie : GREEN'
    Write-Host 'Receipt-inventory : GREEN'
    Write-Host 'Release-B backend : GREEN'
    Write-Host 'Werkmap/fixtures  : CLEAN'
    exit 0
}
catch {
    $runFailed = $true
    Write-Host ''
    Write-Host '==================================================' -ForegroundColor Red
    Write-Host ' RELEASE B PRE-MERGE TESTSET ROOD - STOP' -ForegroundColor Red
    Write-Host '==================================================' -ForegroundColor Red
    Write-Host ("Oorzaak: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
