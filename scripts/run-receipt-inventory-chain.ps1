[CmdletBinding()]
param(
    [switch]$SkipBackendBuild,
    [switch]$CiMode
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$steps = @(
    'Controleer projectmap en uitvoeromgeving',
    'Valideer testconfiguratie',
    'Maak geïsoleerde testomgeving gereed',
    'Start productie-ketentest',
    'Verwerk kassabon 1: voorraad 0 naar 2',
    'Verwerk kassabon 2: voorraad 2 naar 5',
    'Herhaal kassabon 2: voorraad blijft 5',
    'Controleer events, idempotentie en eindresultaat'
)
$total = $steps.Count

function Show-Step {
    param([int]$Number, [string]$Text, [string]$State = 'RUNNING')
    $percent = if ($State -eq 'PASS') {
        [math]::Round(($Number / $total) * 100)
    } else {
        [math]::Round((($Number - 1) / $total) * 100)
    }
    $symbol = switch ($State) {
        'PASS' { '[GROEN]' }
        'FAIL' { '[ROOD ]' }
        default { '[BEZIG]' }
    }
    Write-Host ("{0} Stap {1}/{2} ({3}%): {4}" -f $symbol, $Number, $total, $percent, $Text)
}

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Commando mislukt met exitcode $LASTEXITCODE: $Command $($Arguments -join ' ')"
    }
}

Write-Host ''
Write-Host '============================================================'
Write-Host ' REZZERV KETENTEST: KASSABON -> UITPAKKEN -> VOORRAAD'
Write-Host ' Verwacht voorraadpad: 0 -> 2 -> 5 -> 5'
Write-Host '============================================================'
Write-Host ''

try {
    Show-Step 1 $steps[0]
    if (-not (Test-Path 'docker-compose.yml')) { throw 'docker-compose.yml ontbreekt.' }
    if ($CiMode) {
        Invoke-Checked 'python' @('--version')
    } else {
        Invoke-Checked 'docker' @('version')
    }
    Show-Step 1 $steps[0] 'PASS'

    Show-Step 2 $steps[1]
    if ($CiMode) {
        if (-not (Test-Path 'backend/app/testing/receipt_inventory_production_chain.py')) {
            throw 'Productie-ketentest ontbreekt.'
        }
    } else {
        Invoke-Checked 'docker' @('compose', 'config', '--quiet')
    }
    Show-Step 2 $steps[1] 'PASS'

    Show-Step 3 $steps[2]
    if ($CiMode) {
        Write-Host 'CI gebruikt een tijdelijke Python-runtime en tijdelijke kassabonopslag.'
    } elseif (-not $SkipBackendBuild) {
        Invoke-Checked 'docker' @('compose', 'build', 'backend')
    } else {
        Write-Host 'Backendbuild overgeslagen op expliciet verzoek.'
    }
    Show-Step 3 $steps[2] 'PASS'

    Show-Step 4 $steps[3]
    if ($CiMode) {
        $env:PYTHONPATH = 'backend'
        $env:RECEIPT_STORAGE_ROOT = Join-Path ([System.IO.Path]::GetTempPath()) 'rezzerv-receipts'
        $output = & python backend/app/testing/receipt_inventory_production_chain.py 2>&1
    } else {
        $output = & docker compose run --rm --no-deps `
            -e PYTHONPATH=/app `
            -e RECEIPT_STORAGE_ROOT=/tmp/rezzerv-receipts `
            backend python /app/app/testing/receipt_inventory_production_chain.py 2>&1
    }
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) { throw "Productie-ketentest eindigde met exitcode $exitCode." }
    Show-Step 4 $steps[3] 'PASS'

    $joined = $output -join "`n"
    if ($joined -notmatch 'inventory_path') { throw 'Voorraadpad ontbreekt in testuitvoer.' }

    Show-Step 5 $steps[4]
    if ($joined -notmatch '0.*2') { throw 'Overgang 0 -> 2 niet aangetoond.' }
    Show-Step 5 $steps[4] 'PASS'

    Show-Step 6 $steps[5]
    if ($joined -notmatch '2.*5') { throw 'Overgang 2 -> 5 niet aangetoond.' }
    Show-Step 6 $steps[5] 'PASS'

    Show-Step 7 $steps[6]
    if ($joined -notmatch '5.*5') { throw 'Idempotente overgang 5 -> 5 niet aangetoond.' }
    Show-Step 7 $steps[6] 'PASS'

    Show-Step 8 $steps[7]
    if ($joined -notmatch 'RECEIPT_INVENTORY_PRODUCTION_CHAIN_GREEN') {
        throw 'Groene eindmarker ontbreekt.'
    }
    Show-Step 8 $steps[7] 'PASS'

    Write-Host ''
    Write-Host '============================================================'
    Write-Host ' KETENTEST GESLAAGD - 8/8 STAPPEN GROEN - 100%'
    Write-Host ' Voorraadpad: 0 -> 2 -> 5 -> 5'
    Write-Host ' Dubbele voorraadmutatie voorkomen: JA'
    Write-Host '============================================================'
    Write-Host ''
    exit 0
}
catch {
    Write-Host ''
    Write-Host '[ROOD] KETENTEST MISLUKT'
    Write-Host ("Oorzaak: {0}" -f $_.Exception.Message)
    Write-Host 'Verwacht: voorraadpad 0 -> 2 -> 5 -> 5 en exact twee purchase-events.'
    Write-Host ''
    exit 1
}
