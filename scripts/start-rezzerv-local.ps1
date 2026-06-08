param(
  [string]$ConfigPath = ".\config\deployment\rezzerv-local-startup.config.json",
  [switch]$SkipPull,
  [switch]$SkipRegression,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

function Write-Step($message) {
  Write-Host ""
  Write-Host "=== $message ===" -ForegroundColor Cyan
}

function Stop-PortProcesses($ports) {
  foreach ($port in $ports) {
    $ids = netstat -ano |
      Select-String ":$port" |
      ForEach-Object { ($_ -split "\s+")[-1] } |
      Where-Object { $_ -match "^\d+$" -and $_ -ne "0" } |
      Sort-Object -Unique

    foreach ($id in $ids) {
      Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }

    if ($ids) {
      Write-Host "Gestopt op poort ${port}: $($ids -join ', ')"
    } else {
      Write-Host "Geen proces op poort $port"
    }
  }
}

if (!(Test-Path $ConfigPath)) {
  throw "Configuratiebestand niet gevonden: $ConfigPath"
}

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$projectRoot = $config.projectRoot
$frontendPort = [int]$config.ports.frontend
$backendPort = [int]$config.ports.backend
$stableBranch = $config.stableBranch

Write-Step "Ga naar projectroot"
Set-Location $projectRoot
Write-Host "Projectroot: $(Get-Location)"

Write-Step "Branch controleren"
$currentBranch = git branch --show-current
Write-Host "Actieve branch: $currentBranch"

Write-Step "Werkmapstatus controleren"
$status = git status --short
if ($status) {
  Write-Host $status -ForegroundColor Yellow
  throw "Werkmap bevat wijzigingen. Commit, stash of restore eerst bewust voordat de opstartprocedure verder gaat."
}
Write-Host "Werkmap schoon."

if (-not $SkipPull) {
  Write-Step "Pull uitvoeren"
  git pull origin $currentBranch
} else {
  Write-Step "Pull overgeslagen"
}

Write-Step "Oude Rezzerv-processen stoppen"
Stop-PortProcesses @($frontendPort, $backendPort)

if (-not $SkipBuild) {
  Write-Step "Frontend build"
  Set-Location (Join-Path $projectRoot $config.frontend.workingDirectory)
  npm run build
  Set-Location $projectRoot
} else {
  Write-Step "Frontend build overgeslagen"
}

if (-not $SkipRegression) {
  Write-Step "Regressiecontrole"
  & $config.regression.command
} else {
  Write-Step "Regressiecontrole overgeslagen"
}

Write-Step "Backend starten"
$backendCommand = "cd '$projectRoot'; `$env:PYTHONPATH='$($config.backend.pythonPath)'; $($config.backend.command)"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand

Write-Step "Frontend starten"
$frontendRoot = Join-Path $projectRoot $config.frontend.workingDirectory
$frontendCommand = "cd '$frontendRoot'; $($config.frontend.devCommand)"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand

Write-Step "Klaar voor browsercontrole"
Write-Host "Frontend: $($config.frontend.url)"
Write-Host "Kassa:    $($config.frontend.kassaUrl)"
Write-Host "Backend:  $($config.backend.url)"
Write-Host "Swagger:  $($config.backend.docsUrl)"
Write-Host "Gebruik Ctrl+F5 in de browser en voer zo nodig de runtimecheck uit uit docs/deployment/REZZERV_LOCAL_STARTUP_PROCEDURE.md."

