[CmdletBinding()]
param(
    [string]$Branch = ''
)

CLS
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

try {
    Write-Host '==================================================' -ForegroundColor Cyan
    Write-Host ' REZZERV RECEIPT LIFECYCLE - PRE-MERGE ACCEPTATIE' -ForegroundColor Cyan
    Write-Host '==================================================' -ForegroundColor Cyan

    Write-Host ''
    Write-Host '[1/8] Git-branch, remote head en schone werkmap controleren' -ForegroundColor Cyan
    git fetch origin
    if ($LASTEXITCODE -ne 0) { throw 'git fetch mislukt.' }

    $currentBranch = (git branch --show-current).Trim()
    if (-not $currentBranch) { throw 'Geen actieve Git-branch gevonden.' }
    if ($Branch -and $currentBranch -ne $Branch) {
        throw "Verkeerde branch: $currentBranch. Verwacht: $Branch"
    }
    if (-not $Branch) { $Branch = $currentBranch }

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
    Write-Host "[PASS] branch: $Branch" -ForegroundColor Green
    Write-Host "[PASS] head  : $head" -ForegroundColor Green

    Write-Host ''
    Write-Host '[2/8] Docker-runtime volledig opnieuw opbouwen' -ForegroundColor Cyan
    docker compose down
    if ($LASTEXITCODE -ne 0) { throw 'docker compose down mislukt.' }
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up -d --build mislukt.' }
    Start-Sleep -Seconds 90
    docker compose ps
    if ($LASTEXITCODE -ne 0) { throw 'docker compose ps mislukt.' }
    Write-Host '[PASS] runtime opnieuw opgebouwd' -ForegroundColor Green

    Write-Host ''
    Write-Host '[3/8] Backend-health controleren' -ForegroundColor Cyan
    try {
        $health = Invoke-RestMethod http://localhost:8011/api/health
    }
    catch {
        Write-Host '[INFO] localhost-health faalde; backendlog wordt gecontroleerd.' -ForegroundColor Yellow
        docker compose logs backend --tail=200
        try {
            $health = Invoke-RestMethod http://127.0.0.1:8011/api/health
        }
        catch {
            throw 'Backend-health faalt via zowel localhost als 127.0.0.1.'
        }
    }
    Write-Host ("[PASS] backend health: {0}" -f ($health | ConvertTo-Json -Compress)) -ForegroundColor Green

    Write-Host ''
    Write-Host '[4/8] Centrale frontendregressie uitvoeren' -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'run-frontend-regression-report.ps1') -SkipDockerBuild
    if ($LASTEXITCODE -ne 0) {
        throw "Centrale frontendregressie is rood met exitcode $LASTEXITCODE."
    }
    Write-Host '[PASS] centrale frontendregressie groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '[5/8] Receipt -> Voorraad -> Bijna-op ketentest V2' -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'run-receipt-inventory-chain-v2.ps1') -SkipBackendBuild
    if ($LASTEXITCODE -ne 0) {
        throw "Receipt-inventory ketentest V2 is rood met exitcode $LASTEXITCODE."
    }
    Write-Host '[PASS] receipt-inventory keten groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '[6/8] Gerichte backend- en eligibility-regressietests' -ForegroundColor Cyan
    docker compose run --rm --no-deps `
        -e PYTHONPATH=/app `
        -v "${root}/backend/app:/backend/app:ro" `
        -v "${root}/backend/tests:/backend/tests:ro" `
        -v "${root}/frontend/src:/frontend/src:ro" `
        backend sh -lc "python -m pip install --disable-pip-version-check -q pytest && python -m pytest -q tests/test_receipt_lifecycle_foundation.py tests/test_receipt_reimport_lineage_service.py tests/test_receipt_lifecycle_release_b_chain.py tests/test_unpacking_readiness_article_model_contract.py tests/test_receipt_inventory_eligibility.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Gerichte backend/eligibility-regressietests zijn rood met exitcode $LASTEXITCODE."
    }
    Write-Host '[PASS] backend + eligibility regressietests groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '[7/8] Diff-, fixture- en werkmaphygiëne controleren' -ForegroundColor Cyan
    git fetch origin main
    if ($LASTEXITCODE -ne 0) { throw 'Actuele main kon niet worden opgehaald.' }

    git --no-pager diff --check origin/main...HEAD
    if ($LASTEXITCODE -ne 0) { throw 'git diff --check tegen main is rood.' }

    if (git status --porcelain) {
        git status --short
        throw 'Testfase heeft lokale repositorywijzigingen of testartefacten achtergelaten.'
    }
    Write-Host '[PASS] geen diff-, fixture- of werkmapvervuiling' -ForegroundColor Green

    Write-Host ''
    Write-Host '[8/8] Eindstatus en PO-routes' -ForegroundColor Cyan
    Write-Host '==================================================' -ForegroundColor Green
    Write-Host ' RECEIPT PRE-MERGE TESTSET VOLLEDIG GROEN' -ForegroundColor Green
    Write-Host '==================================================' -ForegroundColor Green
    Write-Host "Branch             : $Branch"
    Write-Host "Geteste commit     : $head"
    Write-Host 'Docker rebuild     : GREEN'
    Write-Host 'Backend health     : GREEN'
    Write-Host 'Frontendregressie  : GREEN'
    Write-Host 'Receipt-inventory  : GREEN'
    Write-Host 'Eligibility backend: GREEN'
    Write-Host 'Werkmap/fixtures   : CLEAN'
    Write-Host ''
    Write-Host 'PO functionele controle:'
    Write-Host '  Kassa       : http://localhost:5174/kassa'
    Write-Host '  Uitpakken   : http://localhost:5174/kassabonnen'
    Write-Host '  Voorraad    : http://localhost:5174/voorraad'
    Write-Host '  Spaartegoeden: open via de actiebutton in Rezzerv'
    Write-Host ''
    Write-Host 'Controleer met een echte bon:'
    Write-Host '  - fysieke artikelen WEL in Uitpakken'
    Write-Host '  - koop/spaarzegels NIET in Uitpakken, WEL via Spaartegoeden'
    Write-Host '  - statiegeld/emballage NIET in Uitpakken'
    Write-Host '  - verzend/bezorgkosten NIET in Uitpakken'
    Write-Host '  - korting/totaal/betaling/BTW NIET in Uitpakken'
    exit 0
}
catch {
    Write-Host ''
    Write-Host '==================================================' -ForegroundColor Red
    Write-Host ' RECEIPT PRE-MERGE TESTSET ROOD - STOP' -ForegroundColor Red
    Write-Host '==================================================' -ForegroundColor Red
    Write-Host ("Oorzaak: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
