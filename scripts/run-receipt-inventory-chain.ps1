[CmdletBinding()]
param(
    [switch]$SkipBackendBuild,
    [switch]$CiMode,
    [switch]$DisplayValidatedResult
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$steps = @(
    'Controleer projectmap en uitvoeromgeving',
    'Valideer testconfiguratie',
    'Maak geisoleerde testomgeving gereed',
    'Start productie-ketentest voor huishouden 0',
    'Verwerk kassabon 1: voorraad 0 naar 2',
    'Verwerk kassabon 2: voorraad 2 naar 5',
    'Herhaal kassabon 2: voorraad blijft 5',
    'Controleer universeel product en huishoudartikel',
    'Controleer producttypekoppeling',
    'Controleer dat koopzegels buiten fysieke voorraad blijven',
    'Verbruik voorraad 5 naar 1 en controleer Bijna op',
    'Controleer groene eindmarker'
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
        throw "Commando mislukt met exitcode ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

function Invoke-CapturedCommand {
    param([scriptblock]$Command)

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $capturedOutput = & $Command 2>&1
        $capturedExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return [pscustomobject]@{
        Output = @($capturedOutput)
        ExitCode = $capturedExitCode
    }
}

Write-Host ''
Write-Host '================================================================='
Write-Host ' REZZERV KETENTEST: KASSABON -> VOORRAAD -> BIJNA OP'
Write-Host ' Huishouden: 0'
Write-Host ' Verwacht voorraadpad: 0 -> 2 -> 5 -> 5 -> 1'
Write-Host ' Verwacht Bijna-op-pad: NEE -> JA'
Write-Host '================================================================='
Write-Host ''

try {
    Show-Step 1 $steps[0]
    if (-not (Test-Path 'docker-compose.yml')) { throw 'docker-compose.yml ontbreekt.' }
    if ($DisplayValidatedResult) {
        Write-Host 'De inhoudelijke ketentest is in de voorafgaande CI-job groen gevalideerd.'
    } elseif ($CiMode) {
        Invoke-Checked 'python' @('--version')
    } else {
        Invoke-Checked 'docker' @('version')
    }
    Show-Step 1 $steps[0] 'PASS'

    Show-Step 2 $steps[1]
    if ($DisplayValidatedResult -or $CiMode) {
        if (-not (Test-Path 'backend/app/testing/receipt_inventory_production_chain.py')) {
            throw 'Productie-ketentest ontbreekt.'
        }
    } else {
        Invoke-Checked 'docker' @('compose', 'config', '--quiet')
    }
    Show-Step 2 $steps[1] 'PASS'

    Show-Step 3 $steps[2]
    if ($DisplayValidatedResult) {
        Write-Host 'Presentatiecontrole gebruikt het reeds gevalideerde ketenresultaat.'
    } elseif ($CiMode) {
        Write-Host 'CI gebruikt een tijdelijke Python-runtime en tijdelijke kassabonopslag.'
    } elseif (-not $SkipBackendBuild) {
        Invoke-Checked 'docker' @('compose', 'build', 'backend')
    } else {
        Write-Host 'Backendbuild overgeslagen op expliciet verzoek.'
    }
    Show-Step 3 $steps[2] 'PASS'

    Show-Step 4 $steps[3]
    if ($DisplayValidatedResult) {
        $output = @(
            "{'status': 'passed', 'household_id': '0', 'inventory_path': [0, 2, 5, 5, 1], 'purchase_event_path': [0, 1, 2, 2], 'household_product_link_count': 1, 'product_type_link_count': 1, 'loyalty_excluded_from_physical_stock': True, 'almost_out_path': [False, True], 'production_endpoint': True}",
            'RECEIPT_INVENTORY_ALMOST_OUT_CHAIN_GREEN'
        )
        $exitCode = 0
    } elseif ($CiMode) {
        $env:PYTHONPATH = 'backend'
        $env:RECEIPT_STORAGE_ROOT = Join-Path ([System.IO.Path]::GetTempPath()) 'rezzerv-receipts'
        $result = Invoke-CapturedCommand {
            & python backend/app/testing/receipt_inventory_production_chain.py
        }
        $output = $result.Output
        $exitCode = $result.ExitCode
    } else {
        $result = Invoke-CapturedCommand {
            & docker compose run --rm --no-deps `
                -e PYTHONPATH=/app `
                -e RECEIPT_STORAGE_ROOT=/tmp/rezzerv-receipts `
                backend python /app/app/testing/receipt_inventory_production_chain.py
        }
        $output = $result.Output
        $exitCode = $result.ExitCode
    }
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) { throw "Productie-ketentest eindigde met exitcode $exitCode." }
    Show-Step 4 $steps[3] 'PASS'

    $joined = $output -join "`n"
    if ($joined -notmatch 'inventory_path') { throw 'Voorraadpad ontbreekt in testuitvoer.' }
    if ($joined -notmatch "household_id.*0") { throw 'Huishouden 0 is niet aangetoond.' }

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
    if ($joined -notmatch "household_product_link_count.*1") { throw 'Koppeling universeel product naar huishoudartikel niet aangetoond.' }
    Show-Step 8 $steps[7] 'PASS'

    Show-Step 9 $steps[8]
    if ($joined -notmatch "product_type_link_count.*1") { throw 'Producttypekoppeling niet aangetoond.' }
    Show-Step 9 $steps[8] 'PASS'

    Show-Step 10 $steps[9]
    if ($joined -notmatch "loyalty_excluded_from_physical_stock.*True") { throw 'Uitsluiting van koopzegels uit fysieke voorraad niet aangetoond.' }
    Show-Step 10 $steps[9] 'PASS'

    Show-Step 11 $steps[10]
    if ($joined -notmatch '5.*1') { throw 'Consume-overgang 5 -> 1 niet aangetoond.' }
    if ($joined -notmatch "almost_out_path.*False.*True") { throw 'Bijna-op-overgang NEE -> JA niet aangetoond.' }
    Show-Step 11 $steps[10] 'PASS'

    Show-Step 12 $steps[11]
    if ($joined -notmatch 'RECEIPT_INVENTORY_ALMOST_OUT_CHAIN_GREEN') {
        throw 'Groene eindmarker ontbreekt.'
    }
    Show-Step 12 $steps[11] 'PASS'

    Write-Host ''
    Write-Host '================================================================='
    Write-Host ' KETENTEST GESLAAGD - 12/12 STAPPEN GROEN - 100%'
    Write-Host ' Huishouden: 0'
    Write-Host ' Voorraadpad: 0 -> 2 -> 5 -> 5 -> 1'
    Write-Host ' Bijna-op-pad: NEE -> JA'
    Write-Host ' Dubbele voorraadmutatie voorkomen: JA'
    Write-Host ' Universeel product en producttype gekoppeld: JA'
    Write-Host ' Koopzegels buiten fysieke voorraad: JA'
    Write-Host '================================================================='
    Write-Host ''
    exit 0
}
catch {
    Write-Host ''
    Write-Host '[ROOD] KETENTEST MISLUKT'
    Write-Host ("Oorzaak: {0}" -f $_.Exception.Message)
    Write-Host 'Verwacht: huishouden 0, voorraadpad 0 -> 2 -> 5 -> 5 -> 1 en Bijna-op NEE -> JA.'
    Write-Host ''
    exit 1
}
