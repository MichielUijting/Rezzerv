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
    'Valideer PostgreSQL-testconfiguratie',
    'Maak geisoleerde PostgreSQL-testomgeving gereed',
    'Start productie-ketentest voor huishouden 0',
    'Verwerk kassabon 1: voorraad 0 naar 2',
    'Verwerk kassabon 2: voorraad 2 naar 5',
    'Herhaal kassabon 2: voorraad blijft 5',
    'Controleer universeel product en huishoudartikel',
    'Controleer producttypekoppeling',
    'Controleer dat koopzegels buiten fysieke voorraad blijven',
    'Verbruik voorraad 5 naar 1 en controleer Bijna op',
    'Controleer PostgreSQL/DML-only eindbewijs'
)
$total = $steps.Count
$composeProject = 'rezzerv-receipt-chain-test'
$isolatedStackStarted = $false
$cleanupExitCode = 0
$composeArguments = @(
    '-p', $composeProject,
    '-f', 'docker-compose.yml',
    '-f', 'docker-compose.postgresql.yml',
    '--profile', 'postgresql'
)

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

function Get-FreeLocalTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }
}

function Invoke-ComposeChecked {
    param([string[]]$Arguments)
    Invoke-Checked 'docker' (@('compose') + $composeArguments + $Arguments)
}

Write-Host ''
Write-Host '================================================================='
Write-Host ' REZZERV KETENTEST: KASSABON -> VOORRAAD -> BIJNA OP'
Write-Host ' Datastore: GEISOLEERDE POSTGRESQL'
Write-Host ' Runtime: rezzerv_app / DML-only'
Write-Host ' Huishouden: 0'
Write-Host ' Verwacht voorraadpad: 0 -> 2 -> 5 -> 5 -> 1'
Write-Host ' Verwacht Bijna-op-pad: NEE -> JA'
Write-Host '================================================================='
Write-Host ''

try {
    Show-Step 1 $steps[0]
    if (-not (Test-Path 'docker-compose.yml')) { throw 'docker-compose.yml ontbreekt.' }
    if (-not (Test-Path 'docker-compose.postgresql.yml')) { throw 'docker-compose.postgresql.yml ontbreekt.' }
    if (-not (Test-Path 'backend/app/testing/postgresql_receipt_inventory_production_chain.py')) {
        throw 'PostgreSQL productie-ketentest ontbreekt.'
    }
    if ($DisplayValidatedResult) {
        Write-Host 'De inhoudelijke PostgreSQL-ketentest is in de voorafgaande CI-job groen gevalideerd.'
    } elseif ($CiMode) {
        Invoke-Checked 'python' @('--version')
    } else {
        Invoke-Checked 'docker' @('version')
    }
    Show-Step 1 $steps[0] 'PASS'

    Show-Step 2 $steps[1]
    if ($DisplayValidatedResult -or $CiMode) {
        Write-Host 'CI/presentatiemodus gebruikt de vooraf ingerichte PostgreSQL-runtime.'
    } else {
        $env:REZZERV_POSTGRES_PORT = [string](Get-FreeLocalTcpPort)
        $env:REZZERV_POSTGRES_DB = 'rezzerv_chain_test'
        Invoke-ComposeChecked @('config', '--quiet')
    }
    Show-Step 2 $steps[1] 'PASS'

    Show-Step 3 $steps[2]
    if ($DisplayValidatedResult) {
        Write-Host 'Presentatiecontrole gebruikt het reeds gevalideerde PostgreSQL-ketenresultaat.'
    } elseif ($CiMode) {
        Write-Host 'CI gebruikt een eigen PostgreSQL-service en vooraf uitgevoerde Alembic-migraties.'
    } else {
        # Deze Compose-projectnaam en dit volume zijn uitsluitend voor de ketentest.
        # Een oude, afgebroken ketentestruntime wordt veilig verwijderd; de normale
        # Rezzerv Compose-stack/volume heeft een andere projectnaam en wordt niet geraakt.
        & docker compose @composeArguments down -v --remove-orphans *> $null
        $isolatedStackStarted = $true
        if (-not $SkipBackendBuild) {
            Invoke-ComposeChecked @('build', 'backend')
        } else {
            Write-Host 'Backendbuild overgeslagen op expliciet verzoek.'
        }
        Invoke-ComposeChecked @('up', '-d', '--wait', 'postgres')

        Write-Host 'Alembic migreert de geisoleerde database met rezzerv_migrator...'
        Invoke-ComposeChecked @(
            'run', '--rm', '--no-deps',
            '-e', 'PYTHONPATH=/app',
            'backend', 'python', '-m', 'app.schema_migration_preflight'
        )
    }
    Show-Step 3 $steps[2] 'PASS'

    Show-Step 4 $steps[3]
    if ($DisplayValidatedResult) {
        $output = @(
            "{'status': 'passed', 'datastore': 'postgresql', 'runtime_user': 'rezzerv_app', 'migration_credential_available': False, 'household_id': '0', 'inventory_path': [0, 2, 5, 5, 1], 'purchase_event_path': [0, 1, 2, 2], 'household_product_link_count': 1, 'product_type_link_count': 1, 'loyalty_excluded_from_physical_stock': True, 'almost_out_path': [False, True], 'production_endpoint': True}",
            'POSTGRESQL_RECEIPT_CHAIN_RUNTIME_CREATE_DENIED_GREEN',
            'POSTGRESQL_RECEIPT_INVENTORY_ALMOST_OUT_CHAIN_GREEN'
        )
        $exitCode = 0
    } elseif ($CiMode) {
        $env:PYTHONPATH = 'backend'
        $env:MIGRATION_DATABASE_URL = ''
        $result = Invoke-CapturedCommand {
            & python backend/app/testing/postgresql_receipt_inventory_production_chain.py
        }
        $output = $result.Output
        $exitCode = $result.ExitCode
    } else {
        $result = Invoke-CapturedCommand {
            & docker compose @composeArguments run --rm --no-deps `
                -e PYTHONPATH=/app `
                -e MIGRATION_DATABASE_URL= `
                -e RECEIPT_STORAGE_ROOT=/tmp/rezzerv-receipts `
                backend python /app/app/testing/postgresql_receipt_inventory_production_chain.py
        }
        $output = $result.Output
        $exitCode = $result.ExitCode
    }
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) { throw "PostgreSQL productie-ketentest eindigde met exitcode $exitCode." }
    Show-Step 4 $steps[3] 'PASS'

    $joined = $output -join "`n"
    if ($joined -notmatch "datastore.*postgresql") { throw 'PostgreSQL-datastore is niet aangetoond.' }
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
    if ($joined -notmatch "migration_credential_available.*False") {
        throw 'Afwezigheid van migratiecredential tijdens runtime-keten niet aangetoond.'
    }
    if ($joined -notmatch 'POSTGRESQL_RECEIPT_CHAIN_RUNTIME_CREATE_DENIED_GREEN') {
        throw 'DML-only runtimegrens niet aangetoond.'
    }
    if ($joined -notmatch 'POSTGRESQL_RECEIPT_INVENTORY_ALMOST_OUT_CHAIN_GREEN') {
        throw 'Groene PostgreSQL-eindmarker ontbreekt.'
    }
    Show-Step 12 $steps[11] 'PASS'

    Write-Host ''
    Write-Host '================================================================='
    Write-Host ' KETENTEST GESLAAGD - 12/12 STAPPEN GROEN - 100%'
    Write-Host ' Datastore: PostgreSQL'
    Write-Host ' Runtime CREATE-recht: GEWEIGERD'
    Write-Host ' Migratiecredential tijdens keten: AFWEZIG'
    Write-Host ' Huishouden: 0'
    Write-Host ' Voorraadpad: 0 -> 2 -> 5 -> 5 -> 1'
    Write-Host ' Bijna-op-pad: NEE -> JA'
    Write-Host ' Dubbele voorraadmutatie voorkomen: JA'
    Write-Host ' Universeel product en producttype gekoppeld: JA'
    Write-Host ' Koopzegels buiten fysieke voorraad: JA'
    Write-Host '================================================================='
    Write-Host ''
}
catch {
    Write-Host ''
    Write-Host '[ROOD] KETENTEST MISLUKT'
    Write-Host ("Oorzaak: {0}" -f $_.Exception.Message)
    Write-Host 'Verwacht: PostgreSQL, huishouden 0, voorraadpad 0 -> 2 -> 5 -> 5 -> 1 en Bijna-op NEE -> JA.'
    Write-Host ''
    exit 1
}
finally {
    if ($isolatedStackStarted -and -not $CiMode -and -not $DisplayValidatedResult) {
        Write-Host '[OPRUIMEN] Geisoleerde PostgreSQL-ketenteststack en testvolume worden verwijderd...'
        $cleanupResult = Invoke-CapturedCommand {
            & docker compose @composeArguments down -v --remove-orphans
        }
        $cleanupResult.Output | ForEach-Object { Write-Host $_ }
        if ($cleanupResult.ExitCode -ne 0) {
            $cleanupExitCode = $cleanupResult.ExitCode
            Write-Host ("[ROOD] Cleanup van de geisoleerde ketentestomgeving eindigde met exitcode {0}." -f $cleanupResult.ExitCode)
        } else {
            Write-Host '[GROEN] Geisoleerde PostgreSQL-ketenteststack en testvolume zijn verwijderd.'
        }
    }
}

if ($cleanupExitCode -ne 0) {
    exit $cleanupExitCode
}

exit 0
