param(
  [switch]$SkipDockerBuild
)

CLS

$ErrorActionPreference = "Stop"

Write-Host "=== Rezzerv centrale frontendregressie ===" -ForegroundColor Cyan

function New-RegressionAuthenticatedSession {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Email,
    [Parameter(Mandatory = $true)]
    [string]$Password,
    [string]$Label = "regressiesessie"
  )

  Write-Host "`n=== Server-side $Label ===" -ForegroundColor Cyan

  $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
  $body = @{
    email = $Email
    password = $Password
  } | ConvertTo-Json

  $login = Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8011/api/auth/login" `
    -ContentType "application/json" `
    -Body $body `
    -WebSession $session

  if (-not $login -or -not $login.email) {
    throw "Server-side $Label kon niet worden vastgesteld."
  }
  if ("$($login.active_household_id)" -ne "0") {
    throw "De centrale regressiesessie moet huishouden 0 gebruiken; ontvangen: $($login.active_household_id)."
  }

  Write-Host "Aangemeld als $($login.email), huishouden $($login.active_household_id), rol $($login.role)." -ForegroundColor Green
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

$superuserEmail = if ($env:REZZERV_REGRESSION_SUPERUSER_EMAIL) {
  $env:REZZERV_REGRESSION_SUPERUSER_EMAIL
} else {
  "supergebruiker@rezzerv.local"
}
$superuserPassword = $env:REZZERV_REGRESSION_SUPERUSER_PASSWORD

if (-not $superuserPassword) {
  throw "REZZERV_REGRESSION_SUPERUSER_PASSWORD ontbreekt. Stel deze tijdelijk in voor de lokale regressierun."
}

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

  $cleanupSession = New-RegressionAuthenticatedSession `
    -Email $superuserEmail `
    -Password $superuserPassword `
    -Label "platform-regressiesessie"
  Invoke-RegressionFixtureCleanup -WebSession $cleanupSession

  Write-Host "`n=== Playwright frontend regressie via Docker ===" -ForegroundColor Cyan
  Write-Host "Canonieke supergebruiker: $superuserEmail; regressiehuishouden: 0" -ForegroundColor Cyan
  Write-Host "Ledenfixture: lid@rezzerv.local; rol: household.member" -ForegroundColor Cyan

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
    -e PLAYWRIGHT_SUPERUSER_EMAIL=$superuserEmail `
    -e PLAYWRIGHT_SUPERUSER_PASSWORD=$superuserPassword `
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
    $cleanupSession = New-RegressionAuthenticatedSession `
      -Email $superuserEmail `
      -Password $superuserPassword `
      -Label "platform-regressiesessie"
    Invoke-RegressionFixtureCleanup -WebSession $cleanupSession
  } catch {
    Write-Host "Regression fixture cleanup na test faalde: $($_.Exception.Message)" -ForegroundColor Red
    if ($LASTEXITCODE -eq 0) {
      $global:LASTEXITCODE = 1
    }
  }
  Pop-Location
}
