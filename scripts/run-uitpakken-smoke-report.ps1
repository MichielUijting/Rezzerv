param(
  [switch]$ShowReport
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

Write-Host "=== Uitpakken smoke-test ===" -ForegroundColor Cyan
Write-Host "Repo: $repoRoot"

$env:PYTHONPATH = $repoRoot.Path

python backend/app/testing/uitpakken_smoke.py

if ($LASTEXITCODE -ne 0) {
  Write-Host "Uitpakken smoke-test: FAILED" -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "Uitpakken smoke-test: PASSED" -ForegroundColor Green

if ($ShowReport) {
  Write-Host ""
  Write-Host "=== Rapport ===" -ForegroundColor Cyan
  Get-Content .\uitpakken_smoke_report.json -Raw
}
