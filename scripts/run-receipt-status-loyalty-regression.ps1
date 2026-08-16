[CmdletBinding()]
param(
    [switch]$SkipBackendBuild
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$backendImage = $null

function Invoke-DockerCaptured {
    param([string[]]$DockerArgs)

    # Docker writes normal progress to stderr. Windows PowerShell 5.1 can turn
    # captured native stderr into ErrorRecords, so judge by the real exit code.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& docker @DockerArgs 2>&1 | ForEach-Object { "$_" })
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return [pscustomobject]@{
        Output = @($output)
        ExitCode = [int]$exitCode
    }
}

function Resolve-RunningBackendImage {
    # The documented main-validation starts Rezzerv with
    # `docker compose up -d --build` before regression runners execute.
    # Resolve the exact image from that running backend service instead of
    # guessing a Compose-generated image name.
    $containerResult = Invoke-DockerCaptured @('compose', 'ps', '-q', 'backend')
    if ($containerResult.ExitCode -ne 0) {
        throw "Draaiende backendcontainer kon niet worden bepaald (exitcode $($containerResult.ExitCode))."
    }

    $containerIds = @(
        $containerResult.Output |
            Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }
    )
    if ($containerIds.Count -lt 1) {
        throw 'Geen draaiende Rezzerv-backend gevonden. Voer eerst de gedocumenteerde main Docker rebuild/start uit: docker compose up -d --build.'
    }

    $containerId = ([string]$containerIds[0]).Trim()
    $inspectResult = Invoke-DockerCaptured @('inspect', '--format', '{{.Image}}', $containerId)
    if ($inspectResult.ExitCode -ne 0) {
        throw "Backendimage van container $containerId kon niet worden gelezen (exitcode $($inspectResult.ExitCode))."
    }

    $imageIds = @(
        $inspectResult.Output |
            Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }
    )
    if ($imageIds.Count -lt 1) {
        throw 'Draaiende backend heeft geen controleerbare Docker image-ID.'
    }

    return ([string]$imageIds[0]).Trim()
}

function Invoke-DisposableBackend {
    param([Parameter(Mandatory=$true)][string]$ShellCommand)

    if ([string]::IsNullOrWhiteSpace([string]$script:backendImage)) {
        throw 'Backendimage is nog niet vastgesteld.'
    }

    # Intentionally use docker run rather than docker compose run. This keeps
    # the normal ./backend/data:/app/data runtime mount completely outside the
    # regression container. It mirrors the existing CI isolation model.
    return Invoke-DockerCaptured @(
        'run', '--rm',
        '-e', 'PYTHONPATH=/app',
        '-e', 'DATABASE_URL=sqlite:////tmp/rezzerv-receipt-status-loyalty.db',
        '-e', 'SQLITE_RUNTIME_VOLUME=local-regression-temp',
        $script:backendImage, 'sh', '-lc', $ShellCommand
    )
}

try {
    Write-Host ''
    Write-Host '================================================================='
    Write-Host ' REZZERV REGRESSIE: RECEIPT STATUS + LOYALTY + SCANNERBOUNDARY'
    Write-Host ' Geisoleerde testdatabase: /tmp/rezzerv-receipt-status-loyalty.db'
    Write-Host ' Normale runtime-datamount: NIET AANGEKOPPELD'
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
        Write-Host '[BEZIG] Backendimage opnieuw bouwen binnen bestaande Rezzerv-teststack'
        docker compose build backend
        if ($LASTEXITCODE -ne 0) {
            throw 'Backendbuild is mislukt.'
        }
        Write-Host '[INFO] De runner gebruikt daarna de image van de reeds draaiende backendservice.'
    }

    $backendImage = Resolve-RunningBackendImage
    Write-Host "[OK] Geisoleerde tests gebruiken exact backendimage $backendImage" -ForegroundColor Green

    Write-Host '[1/4] AH/Picnic supermarket baseline + status/loyalty-contract'
    $supermarket = Invoke-DisposableBackend @'
python -m pip install --disable-pip-version-check -q pytest && \
python -m pytest -s -q \
  tests/test_kassa_supermarket_baseline_gate.py \
  tests/test_pr245_status_and_loyalty_contract.py
'@
    $supermarket.Output | ForEach-Object { Write-Host $_ }
    if ($supermarket.ExitCode -ne 0) {
        throw "Supermarket/status/loyalty-regressie eindigde met exitcode $($supermarket.ExitCode)."
    }
    Write-Host '[PASS] AH/Picnic + status/loyalty groen' -ForegroundColor Green

    Write-Host '[2/4] Scannerboundary compile + contract/persistence-tests'
    $scanner = Invoke-DisposableBackend @'
python -m pip install --disable-pip-version-check -q pytest && \
python -m compileall -q /app/app/integrations/receipt_scanners && \
python -m pytest -q \
  tests/test_receipt_scanner_release_a.py \
  tests/test_receipt_scanner_persistence_compat.py \
  tests/test_pr245_status_and_loyalty_contract.py
'@
    $scanner.Output | ForEach-Object { Write-Host $_ }
    if ($scanner.ExitCode -ne 0) {
        throw "Scannerboundary-regressie eindigde met exitcode $($scanner.ExitCode)."
    }
    Write-Host '[PASS] scannerboundary contract/persistence groen' -ForegroundColor Green

    Write-Host '[3/4] Geen scanner-specifieke dependency-lek in gateway'
    $leakGuard = Invoke-DisposableBackend @'
if grep -R -E 'paddleocr|tesseract|ocrmypdf|profiles\.' /app/app/integrations/receipt_scanners/gateway.py; then
  echo 'SCANNER_GATEWAY_DEPENDENCY_LEAK_FOUND'
  exit 21
fi
echo 'SCANNER_GATEWAY_DEPENDENCY_GUARD_GREEN'
'@
    $leakGuard.Output | ForEach-Object { Write-Host $_ }
    if ($leakGuard.ExitCode -ne 0) {
        throw "Scannerdependency-guard eindigde met exitcode $($leakGuard.ExitCode)."
    }
    if (($leakGuard.Output -join "`n") -notmatch 'SCANNER_GATEWAY_DEPENDENCY_GUARD_GREEN') {
        throw 'Groene scannerdependency-marker ontbreekt.'
    }
    Write-Host '[PASS] geen scannerdependency-lek' -ForegroundColor Green

    Write-Host '[4/4] Legacy adapter is enige production parser-caller achter boundary'
    $callerGuard = Invoke-DisposableBackend @'
grep -F 'from app.services.receipt_service import parse_receipt_content' /app/app/integrations/receipt_scanners/adapters/rezzerv_legacy.py >/dev/null || exit 31
python - <<'PY'
from pathlib import Path
text = Path('/app/app/services/receipt_service.py').read_text(encoding='utf-8')
count = text.count('scan_receipt_content_via_gateway(')
assert count == 2, f'expected exactly 2 scanner gateway calls, found {count}'
print('SCANNER_BOUNDARY_CALLER_GUARD_GREEN')
PY
'@
    $callerGuard.Output | ForEach-Object { Write-Host $_ }
    if ($callerGuard.ExitCode -ne 0) {
        throw "Scanner caller-guard eindigde met exitcode $($callerGuard.ExitCode)."
    }
    if (($callerGuard.Output -join "`n") -notmatch 'SCANNER_BOUNDARY_CALLER_GUARD_GREEN') {
        throw 'Groene scanner caller-marker ontbreekt.'
    }
    Write-Host '[PASS] scannerboundary caller-contract groen' -ForegroundColor Green

    Write-Host ''
    Write-Host '=================================================================' -ForegroundColor Green
    Write-Host ' RECEIPT STATUS + LOYALTY + SCANNERBOUNDARY REGRESSIE = GREEN' -ForegroundColor Green
    Write-Host ' AH/Picnic supermarket baseline : GREEN' -ForegroundColor Green
    Write-Host ' Kassa status/loyalty contract   : GREEN' -ForegroundColor Green
    Write-Host ' Scanner contract/persistence    : GREEN' -ForegroundColor Green
    Write-Host ' Scanner dependency/caller guard : GREEN' -ForegroundColor Green
    Write-Host ' Normale runtime-database gebruikt: NEE' -ForegroundColor Green
    Write-Host '=================================================================' -ForegroundColor Green
    Write-Host ''
    exit 0
}
catch {
    Write-Host ''
    Write-Host '=================================================================' -ForegroundColor Red
    Write-Host ' RECEIPT STATUS + LOYALTY + SCANNERBOUNDARY REGRESSIE = ROOD' -ForegroundColor Red
    Write-Host ("Oorzaak: {0}" -f $_.Exception.Message) -ForegroundColor Red
    Write-Host '=================================================================' -ForegroundColor Red
    Write-Host ''
    exit 1
}
