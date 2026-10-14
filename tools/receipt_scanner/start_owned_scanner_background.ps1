# Starts the repository-owned receipt scanner without a second console.
# The regular Docker startup remains controlled exclusively by start.bat.
param([string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path)
$ErrorActionPreference = 'Stop'
$scanner = Join-Path $RepositoryRoot 'tools\receipt_scanner\meesdeboer_engine\scan_engine.py'
$bridge = Join-Path $RepositoryRoot 'tools\receipt_scanner\inhuis_demo_bridge.py'
$venv = Join-Path $RepositoryRoot 'tools\receipt_scanner\.venv\Scripts\python.exe'
$starter = Join-Path $RepositoryRoot 'start-alternatieve-kassabonscanner.bat'
$logDir = Join-Path $env:LOCALAPPDATA 'Inhuis\scanner'
$log = Join-Path $logDir 'startup.log'

function Test-ScannerHealth {
    try {
        $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8003/health' -TimeoutSec 2
        return ([string]$h.provider -eq 'in-huis-demo' -and [int]$h.bridge_version -ge 3 -and [string]$h.status -eq 'ok')
    } catch { return $false }
}

if (-not (Test-Path $scanner) -or -not (Test-Path $bridge) -or -not (Test-Path $starter)) {
    Write-Host '[ERROR] Inhuis scannerbron of starter ontbreekt.'
    exit 1
}
$listener = Get-NetTCPConnection -LocalPort 8003 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    if (Test-ScannerHealth) {
        Write-Host '[OK] Eigen Inhuis AI-scanner draait al.'
        exit 0
    }
    Write-Host '[ERROR] Poort 8003 is bezet door een andere of oudere scanner. Niets gestopt.'
    exit 1
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
# No process kill, no container changes. Keep logs local, not under source control.
# cmd /c runs the existing official scanner starter. It may populate only its
# dedicated venv with declared packages on first use.
$arguments = '/d /c ""' + $starter + '" > "' + $log + '" 2>&1"'
$env:INHUIS_SCANNER_BACKGROUND = '1'
Start-Process -FilePath $env:ComSpec -ArgumentList $arguments -WindowStyle Hidden | Out-Null
Remove-Item Env:INHUIS_SCANNER_BACKGROUND -ErrorAction SilentlyContinue

for ($i=0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    if (Test-ScannerHealth) {
        Write-Host '[OK] Eigen Inhuis AI-scanner actief op poort 8003.'
        exit 0
    }
    if ((Get-NetTCPConnection -LocalPort 8003 -State Listen -ErrorAction SilentlyContinue) -and -not (Test-ScannerHealth)) {
        Write-Host '[ERROR] Onbekende listener op scannerpoort; niets gestopt.'
        exit 1
    }
}
Write-Host '[ERROR] AI-scanner niet gereed. Zie lokaal log:'
Write-Host $log
exit 1
