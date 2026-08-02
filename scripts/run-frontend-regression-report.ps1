param(
  [switch]$SkipDockerBuild
)

CLS

$ErrorActionPreference = "Stop"

Write-Host "=== Rezzerv centrale frontendregressie ===" -ForegroundColor Cyan

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

$superuserEmail = if ($env:REZZERV_REGRESSION_SUPERUSER_EMAIL) {
  $env:REZZERV_REGRESSION_SUPERUSER_EMAIL
} else {
  "supergebruiker@rezzerv.local"
}
$superuserPassword = $env:REZZERV_REGRESSION_SUPERUSER_PASSWORD
$testAdminEmail = "test-admin@rezzerv.local"
$testAdminPassword = "Rt$([Guid]::NewGuid().ToString('N'))"

if (-not $superuserPassword) {
  throw "REZZERV_REGRESSION_SUPERUSER_PASSWORD ontbreekt. Stel deze tijdelijk in voor de lokale regressierun."
}

try {
  Write-Host "`n=== Huishouden-0 contractscan ===" -ForegroundColor Cyan
  & (Join-Path $PSScriptRoot "assert-household-zero-test-contract.ps1")

  if ($LASTEXITCODE -ne 0) {
    throw "Huishouden-0-contractscan is gefaald met exitcode $LASTEXITCODE."
  }

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

  Write-Host "`n=== Autorisatiematrix server-side sessies ===" -ForegroundColor Cyan
  docker compose exec -T `
    -e REZZERV_TEST_SUPERUSER_EMAIL=$superuserEmail `
    -e REZZERV_TEST_SUPERUSER_PASSWORD=$superuserPassword `
    -e REZZERV_TEST_ADMIN_EMAIL=$testAdminEmail `
    -e REZZERV_TEST_ADMIN_PASSWORD=$testAdminPassword `
    backend python /app/tests/authorization_role_matrix_selftest.py

  if ($LASTEXITCODE -ne 0) {
    throw "Autorisatiematrix-selftest is gefaald met exitcode $LASTEXITCODE."
  }

  Write-Host "`n=== Huishouden-0 regressie-fixtures voorbereiden ===" -ForegroundColor Cyan
  docker compose exec -T backend `
    python /app/tests/household_zero_regression_fixture.py prepare

  if ($LASTEXITCODE -ne 0) {
    throw "Voorbereiden van huishouden-0-fixtures is gefaald met exitcode $LASTEXITCODE."
  }

  Write-Host "`n=== Playwright frontend regressie via Docker ===" -ForegroundColor Cyan
  Write-Host "Platform-superuser: $superuserEmail; huishouden: 0" -ForegroundColor Cyan
  Write-Host "Playwright-testaccount: $testAdminEmail; huishouden: 0" -ForegroundColor Cyan

  $frontendPath = Join-Path $repoRoot "frontend"
  $frontendPath = $frontendPath.Replace("\", "/")

  $testFiles = @(
    "tests/e2e/kassa.frontend-regression.spec.js",
    "tests/e2e/uitpakken.frontend-regression.spec.js",
    "tests/e2e/external-databases.frontend-regression.spec.js",
    "tests/e2e/external-databases-off.frontend-regression.spec.js",
    "tests/e2e/external-databases-unlink.frontend-regression.spec.js",
    "tests/e2e/external-databases-known-gtin.frontend-regression.spec.js",
    "tests/e2e/external-databases-no-redundant-buttons.frontend-regression.spec.js",
    "tests/e2e/product-groups.frontend-regression.spec.js",
    "tests/e2e/settings-article-groups.frontend-regression.spec.js",
    "tests/e2e/article-detail.frontend-regression.spec.js",
    "tests/e2e/catalog-gpc-search.frontend-regression.spec.js"
  ) -join " "

  docker run --rm `
    --add-host=host.docker.internal:host-gateway `
    -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:5174 `
    -e PLAYWRIGHT_API_URL=http://host.docker.internal:8011 `
    -e PLAYWRIGHT_TEST_ADMIN_EMAIL=$testAdminEmail `
    -e PLAYWRIGHT_TEST_ADMIN_PASSWORD=$testAdminPassword `
    -e PLAYWRIGHT_HOUSEHOLD_ID=0 `
    -v "${frontendPath}:/work" `
    -v rezzerv_playwright_node_modules:/work/node_modules `
    -w /work `
    mcr.microsoft.com/playwright:v1.58.2-noble `
    bash -lc "npm ci && ./node_modules/.bin/playwright test --workers=3 $testFiles"

  if ($LASTEXITCODE -ne 0) {
    throw "Playwright frontend regressie is gefaald met exitcode $LASTEXITCODE."
  }

  Write-Host "`n=== Frontend regressie groen ===" -ForegroundColor Green
}
finally {
  try {
    Write-Host "`n=== Huishouden-0 regressie-fixtures opruimen ===" -ForegroundColor Cyan
    docker compose exec -T backend `
      python /app/tests/household_zero_regression_fixture.py cleanup
    if ($LASTEXITCODE -ne 0) {
      throw "Cleanup gaf exitcode $LASTEXITCODE."
    }
  } catch {
    Write-Host "Regression fixture cleanup na test faalde: $($_.Exception.Message)" -ForegroundColor Red
    if ($LASTEXITCODE -eq 0) {
      $global:LASTEXITCODE = 1
    }
  }
  $testAdminPassword = $null
  Pop-Location
}
