param(
  [switch]$ShowReport
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

Write-Host "=== Uitpakken regressietest ===" -ForegroundColor Cyan
Write-Host "Repo: $repoRoot"

$env:PYTHONPATH = $repoRoot.Path

python backend/app/testing/uitpakken_regression.py

if ($LASTEXITCODE -ne 0) {
  Write-Host "Uitpakken regressietest: FAILED" -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "Uitpakken regressietest: PASSED" -ForegroundColor Green

if ($ShowReport) {
  Write-Host ""
  Write-Host "=== Rapport ===" -ForegroundColor Cyan
  Get-Content .\uitpakken_regression_report.json -Raw
}
