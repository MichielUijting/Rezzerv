[CmdletBinding()]
param(
    [string]$Branch = ''
)

CLS
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-NativeProcessWithTimeout {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][int]$TimeoutSec,
        [Parameter(Mandatory = $true)][string]$Label
    )

    Write-Host ("[BEZIG] {0} (harde timeout: {1}s)" -f $Label, $TimeoutSec) -ForegroundColor Cyan
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $root `
        -NoNewWindow `
        -PassThru

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $heartbeatAt = (Get-Date).AddSeconds(10)

    while (-not $process.HasExited) {
        if ((Get-Date) -ge $deadline) {
            Write-Host ("[TIMEOUT] {0} heeft de PowerShell-prompt niet binnen {1}s teruggegeven." -f $Label, $TimeoutSec) -ForegroundColor Red
            try {
                & taskkill /PID $process.Id /T /F | Out-Null
            }
            catch {
                try { $process.Kill() } catch { }
            }
            throw "$Label is afgebroken wegens een proces-timeout."
        }

        if ((Get-Date) -ge $heartbeatAt) {
            $remaining = [math]::Max(0, [int]($deadline - (Get-Date)).TotalSeconds)
            Write-Host ("[WACHT] {0} draait nog; maximaal {1}s resterend." -f $Label, $remaining) -ForegroundColor Yellow
            $heartbeatAt = (Get-Date).AddSeconds(10)
        }

        Start-Sleep -Seconds 1
        $process.Refresh()
    }

    $exitCode = $process.ExitCode
    $process.Dispose()
    if ($exitCode -ne 0) {
        throw "$Label eindigde met exitcode $exitCode."
    }
    Write-Host ("[PASS] {0}" -f $Label) -ForegroundColor Green
}

function Get-RezzervHealth {
    param(
        [int]$TimeoutSec = 5
    )

    foreach ($uri in @('http://localhost:8011/api/health', 'http://127.0.0.1:8011/api/health')) {
        try {
            return Invoke-RestMethod -Uri $uri -TimeoutSec $TimeoutSec
        }
        catch {
            continue
        }
    }
    return $null
}

function Wait-RezzervRuntime {
    param(
        [int]$MaxWaitSec = 120,
        [int]$PollSec = 5
    )

    $deadline = (Get-Date).AddSeconds($MaxWaitSec)
    $attempt = 0

    while ((Get-Date) -lt $deadline) {
        $attempt++
        $elapsed = $MaxWaitSec - [math]::Max(0, [int]($deadline - (Get-Date)).TotalSeconds)
        Write-Host ("[WACHT] runtime readiness - poging {0}, verstreken {1}s/{2}s" -f $attempt, $elapsed, $MaxWaitSec) -ForegroundColor Yellow

        $backendRunning = $false
        $frontendRunning = $false
        try {
            $services = docker compose ps --services --filter status=running 2>$null
            if ($LASTEXITCODE -eq 0) {
                $backendRunning = @($services) -contains 'backend'
                $frontendRunning = @($services) -contains 'frontend'
            }
        }
        catch {
            $backendRunning = $false
            $frontendRunning = $false
        }

        if ($backendRunning -and $frontendRunning) {
            $health = Get-RezzervHealth -TimeoutSec 4
            if ($null -ne $health) {
                Write-Host '[PASS] backend en frontend draaien; backend-health reageert.' -ForegroundColor Green
                return $health
            }
            Write-Host '[INFO] containers draaien; backend-health is nog niet gereed.' -ForegroundColor DarkYellow
        }
        else {
            Write-Host ("[INFO] containers nog niet volledig running (backend={0}, frontend={1})." -f $backendRunning, $frontendRunning) -ForegroundColor DarkYellow
        }

        Start-Sleep -Seconds $PollSec
    }

    Write-Host ''
    Write-Host '[DIAGNOSE] Runtime werd niet tijdig gereed. Containerstatus:' -ForegroundColor Red
    docker compose ps
    Write-Host ''
    Write-Host '[DIAGNOSE] Backendlog (laatste 200 regels):' -ForegroundColor Red
    docker compose logs backend --tail=200
    Write-Host ''
    Write-Host '[DIAGNOSE] Frontendlog (laatste 100 regels):' -ForegroundColor Red
    docker compose logs frontend --tail=100
    throw "Rezzerv-runtime niet gereed binnen $MaxWaitSec seconden."
}

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
    Write-Host '[2/8] Docker-runtime gecontroleerd opnieuw opbouwen' -ForegroundColor Cyan
    Invoke-NativeProcessWithTimeout -FilePath 'docker' -ArgumentList @('compose', 'down') -TimeoutSec 120 -Label 'docker compose down'
    Invoke-NativeProcessWithTimeout -FilePath 'docker' -ArgumentList @('compose', 'build') -TimeoutSec 600 -Label 'docker compose build'
    Invoke-NativeProcessWithTimeout -FilePath 'docker' -ArgumentList @('compose', 'up', '-d', '--no-build', '--wait', '--wait-timeout', '120') -TimeoutSec 180 -Label 'docker compose up + readiness'

    $health = Wait-RezzervRuntime -MaxWaitSec 60 -PollSec 5
    docker compose ps
    if ($LASTEXITCODE -ne 0) { throw 'docker compose ps mislukt.' }
    Write-Host '[PASS] runtime opnieuw opgebouwd en gereed' -ForegroundColor Green

    Write-Host ''
    Write-Host '[3/8] Backend-health bevestigen' -ForegroundColor Cyan
    if ($null -eq $health) {
        $health = Get-RezzervHealth -TimeoutSec 5
    }
    if ($null -eq $health) {
        throw 'Backend-health reageert niet binnen de ingestelde timeout.'
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
    Write-Host '  Kassa        : http://localhost:5174/kassa'
    Write-Host '  Uitpakken    : http://localhost:5174/kassabonnen'
    Write-Host '  Voorraad     : http://localhost:5174/voorraad'
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
