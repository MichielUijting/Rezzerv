[CmdletBinding()]
param(
    [switch]$SkipBackendBuild
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-CapturedDockerPython {
    param([string]$ScriptPath)

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & docker compose run --rm --no-deps `
            -e PYTHONPATH=/app `
            -e RECEIPT_STORAGE_ROOT=/tmp/rezzerv-receipts `
            backend python $ScriptPath 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return [pscustomobject]@{
        Output = @($output)
        ExitCode = $exitCode
    }
}

try {
    Write-Host ''
    Write-Host '================================================================='
    Write-Host ' REZZERV KETENTEST V2: KASSABON -> VOORRAAD -> BIJNA OP'
    Write-Host ' Huishouden: 0'
    Write-Host '================================================================='
    Write-Host ''

    if (-not (Test-Path 'docker-compose.yml')) {
        throw 'docker-compose.yml ontbreekt.'
    }

    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Compose-configuratie is ongeldig.'
    }

    if (-not $SkipBackendBuild) {
        docker compose build backend
        if ($LASTEXITCODE -ne 0) {
            throw 'Backendbuild is mislukt.'
        }
    }

    Write-Host '[BEZIG] Productieketen huishouden 0'
    $chain = Invoke-CapturedDockerPython '/app/app/testing/receipt_inventory_production_chain.py'
    $chain.Output | ForEach-Object { Write-Host $_ }
    if ($chain.ExitCode -ne 0) {
        throw "Productieketen eindigde met exitcode $($chain.ExitCode)."
    }
    $chainText = $chain.Output -join "`n"

    if ($chainText -notmatch "household_id.*0") { throw 'Huishouden 0 niet aangetoond.' }
    if ($chainText -notmatch "inventory_path.*0.*2.*5.*5.*1") { throw 'Voorraadpad 0 -> 2 -> 5 -> 5 -> 1 niet aangetoond.' }
    if ($chainText -notmatch "purchase_event_path.*0.*1.*2.*2") { throw 'Idempotente purchase-events niet aangetoond.' }
    if ($chainText -notmatch "household_product_link_count.*1") { throw 'Universele productkoppeling niet aangetoond.' }
    if ($chainText -notmatch "loyalty_excluded_from_physical_stock.*True") { throw 'Koopzegeluitsluiting niet aangetoond.' }
    if ($chainText -notmatch "almost_out_path.*False.*True") { throw 'Bijna-op-pad NEE -> JA niet aangetoond.' }
    if ($chainText -notmatch 'RECEIPT_INVENTORY_ALMOST_OUT_CHAIN_GREEN') { throw 'Groene ketenmarker ontbreekt.' }

    Write-Host '[BEZIG] Producttypekoppeling via productieservice'
    $productType = Invoke-CapturedDockerPython '/app/app/testing/product_type_link_contract.py'
    $productType.Output | ForEach-Object { Write-Host $_ }
    if ($productType.ExitCode -ne 0) {
        throw "Producttypecontract eindigde met exitcode $($productType.ExitCode)."
    }
    $productTypeText = $productType.Output -join "`n"
    if ($productTypeText -notmatch "product_type_link_count.*1") { throw 'Exact één producttypekoppeling niet aangetoond.' }
    if ($productTypeText -notmatch 'PRODUCT_TYPE_LINK_CONTRACT_GREEN') { throw 'Groene producttypemarker ontbreekt.' }

    Write-Host ''
    Write-Host '================================================================='
    Write-Host ' KETENTEST GESLAAGD - 12/12 STAPPEN GROEN - 100%'
    Write-Host ' Huishouden: 0'
    Write-Host ' Voorraadpad: 0 -> 2 -> 5 -> 5 -> 1'
    Write-Host ' Bijna-op-pad: NEE -> JA'
    Write-Host ' Dubbele voorraadmutatie voorkomen: JA'
    Write-Host ' Universeel product gekoppeld: JA'
    Write-Host ' Producttype gekoppeld via productieservice: JA'
    Write-Host ' Koopzegels buiten fysieke voorraad: JA'
    Write-Host '================================================================='
    Write-Host ''
    exit 0
}
catch {
    Write-Host ''
    Write-Host '[ROOD] KETENTEST V2 MISLUKT'
    Write-Host ("Oorzaak: {0}" -f $_.Exception.Message)
    Write-Host ''
    exit 1
}
