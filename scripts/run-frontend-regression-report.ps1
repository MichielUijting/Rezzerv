CLS

param(
  [switch]$SkipDockerBuild
)

$ErrorActionPreference = "Stop"

Write-Host "=== Rezzerv centrale frontendregressie ===" -ForegroundColor Cyan

function New-RegressionAuthenticatedSession {
  Write-Host "`n=== Server-side regressiesessie ===" -ForegroundColor Cyan

  $email = if ($env:PLAYWRIGHT_SUPERUSER_EMAIL) {
    $env:PLAYWRIGHT_SUPERUSER_EMAIL
  } else {
    "supergebruiker@rezzerv.local"
  }

  $password = if ($env:PLAYWRIGHT_SUPERUSER_PASSWORD) {
    $env:PLAYWRIGHT_SUPERUSER_PASSWORD
  } else {
    "RezzervSuper123!"
  }

  $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
  $body = @{
    email = $email
    password = $password
  } | ConvertTo-Json

  $login = Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8011/api/auth/login" `
    -ContentType "application/json" `
    -Body $body `
    -WebSession $session

  if (-not $login -or -not $login.email) {
    throw "Server-side regressiesessie kon niet worden vastgesteld."
  }

  Write-Host "Aangemeld als $($login.email)." -ForegroundColor Green
  return $session
}

function Invoke-RegressionFixtureCleanup {
  param(
    [Parameter(Mandatory = $true)]
    [Microsoft.PowerShell.Commands.WebRequestSession]$WebSession,
    [int]$MaxAttempts = 5
  )

  Write-Host "`n=== Regression fixture cleanup ===" -ForegroundColor Cyan
  $lastError = $null

  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    try {
      if ($attempt -gt 1) {
        Write-Host "Cleanup opnieuw proberen ($attempt/$MaxAttempts)..." -ForegroundColor Yellow
      }
      Invoke-RestMethod `
        -Method Post `
        -Uri "http://localhost:8011/api/testing/fixtures/cleanup" `
        -WebSession $WebSession | Out-Host
      return
    } catch {
      $lastError = $_
      if ($attempt -lt $MaxAttempts) {
        Start-Sleep -Seconds ([Math]::Min(2 * $attempt, 6))
      }
    }
  }

  throw $lastError
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
$regressionWebSession = $null

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

  $regressionWebSession = New-RegressionAuthenticatedSession
  Invoke-RegressionFixtureCleanup -WebSession $regressionWebSession

  $playwrightEmail = if ($env:REZZERV_PLAYWRIGHT_EMAIL) {
    $env:REZZERV_PLAYWRIGHT_EMAIL
  } else {
    "admin@rezzerv.local"
  }
  $playwrightPassword = $env:REZZERV_PLAYWRIGHT_PASSWORD
  if (-not $playwrightPassword) {
    throw "REZZERV_PLAYWRIGHT_PASSWORD ontbreekt. Stel deze tijdelijk in voor de lokale regressierun."
  }

  Write-Host "`n=== Playwright frontend regressie via Docker ===" -ForegroundColor Cyan
  Write-Host "Playwright-gebruiker: $playwrightEmail; huishouden: 1" -ForegroundColor Cyan

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
    -e PLAYWRIGHT_SUPERUSER_EMAIL=$playwrightEmail `
    -e PLAYWRIGHT_SUPERUSER_PASSWORD=$playwrightPassword `
    -e PLAYWRIGHT_HOUSEHOLD_ID=1 `
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
    $regressionWebSession = New-RegressionAuthenticatedSession
    Invoke-RegressionFixtureCleanup -WebSession $regressionWebSession
  } catch {
    Write-Host "Regression fixture cleanup na test faalde: $($_.Exception.Message)" -ForegroundColor Red
    if ($LASTEXITCODE -eq 0) {
      $global:LASTEXITCODE = 1
    }
  }
  Pop-Location
}
