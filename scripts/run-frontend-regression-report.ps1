param(
  [switch]$SkipDockerBuild
)

$ErrorActionPreference = "Stop"

Write-Host "=== Rezzerv frontend regressie: Kassa + Uitpakken ===" -ForegroundColor Cyan

function Invoke-RegressionFixtureCleanup {
  Write-Host "`n=== Regression fixture cleanup ===" -ForegroundColor Cyan
  $headers = @{ Authorization = "Bearer rezzerv-dev-token::admin@rezzerv.local" }
  Invoke-RestMethod -Method Post -Uri "http://localhost:8011/api/testing/fixtures/cleanup" -Headers $headers | Out-Host
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

try {
  if (-not $SkipDockerBuild) {
    Write-Host "`n=== Docker build/start ===" -ForegroundColor Cyan
    docker compose up -d --build
  }

  Write-Host "`n=== Backend health ===" -ForegroundColor Cyan
  $healthOk = $false
  for ($i = 1; $i -le 12; $i++) {
    try {
      Write-Host "Healthcheck poging $i..."
      Invoke-RestMethod http://localhost:8011/api/health | Out-Host
      $healthOk = $true
      break
    } catch {
      Write-Host "Backend nog niet bereikbaar: $($_.Exception.Message)"
      Start-Sleep -Seconds 10
    }
  }

  if (-not $healthOk) {
    throw "Backend healthcheck niet groen na 12 pogingen."
  }

  Invoke-RegressionFixtureCleanup

  Write-Host "`n=== Playwright frontend regressie via Docker ===" -ForegroundColor Cyan

  $frontendPath = Join-Path $repoRoot "frontend"
  $frontendPath = $frontendPath.Replace("\", "/")

  $testFiles = @(
    "tests/e2e/kassa.frontend-regression.spec.js",
    "tests/e2e/uitpakken.frontend-regression.spec.js",
    "tests/e2e/external-databases.frontend-regression.spec.js",
    "tests/e2e/external-databases-off.frontend-regression.spec.js"
  ) -join " "

  docker run --rm `
    --add-host=host.docker.internal:host-gateway `
    -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:5174 `
    -e PLAYWRIGHT_API_URL=http://host.docker.internal:8011 `
    -v "${frontendPath}:/work" `
    -v rezzerv_playwright_node_modules:/work/node_modules `
    -w /work `
    mcr.microsoft.com/playwright:v1.61.0-noble `
    bash -lc "npm install --package-lock=false && ./node_modules/.bin/playwright test --workers=3 $testFiles"

  if ($LASTEXITCODE -ne 0) {
    throw "Playwright frontend regressie is gefaald met exitcode $LASTEXITCODE."
  }

  Write-Host "`n=== Frontend regressie groen ===" -ForegroundColor Green
}
finally {
  try {
    Invoke-RegressionFixtureCleanup
  } catch {
    Write-Host "Regression fixture cleanup na test faalde: $($_.Exception.Message)" -ForegroundColor Red
    if ($LASTEXITCODE -eq 0) {
      $global:LASTEXITCODE = 1
    }
  }
  Pop-Location
}
