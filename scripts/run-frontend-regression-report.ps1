param(
  [switch]$SkipDockerBuild,
  [int]$FrontendPort = 5174,
  [int]$BackendPort = 8011,
  [string]$ExpectedBranch = ''
)

$ErrorActionPreference = "Stop"

$frontendBaseUrl = "http://localhost:$FrontendPort"
$backendBaseUrl = "http://localhost:$BackendPort"
$playwrightFrontendUrl = "http://host.docker.internal:$FrontendPort"
$playwrightBackendUrl = "http://host.docker.internal:$BackendPort"

Write-Host "=== Rezzerv centrale frontendregressie ===" -ForegroundColor Cyan
Write-Host "Frontend: $frontendBaseUrl"
Write-Host "Backend:  $backendBaseUrl"

function Invoke-RegressionFixtureCleanup {
  param(
    [int]$MaxAttempts = 5
  )

  Write-Host "`n=== Regression fixture cleanup ===" -ForegroundColor Cyan
  $headers = @{ Authorization = "Bearer rezzerv-dev-token::admin@rezzerv.local" }
  $lastError = $null

  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    try {
      if ($attempt -gt 1) {
        Write-Host "Cleanup opnieuw proberen ($attempt/$MaxAttempts)..." -ForegroundColor Yellow
      }
      Invoke-RestMethod -Method Post -Uri "$backendBaseUrl/api/testing/fixtures/cleanup" -Headers $headers | Out-Host
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

try {
  $currentBranch = (git branch --show-current).Trim()
  $currentCommit = (git rev-parse HEAD).Trim()
  Write-Host "Branch:   $currentBranch"
  Write-Host "Commit:   $currentCommit"

  if ($ExpectedBranch -and $currentBranch -ne $ExpectedBranch) {
    throw "Verkeerde branch voor deze regressietest. Verwacht: '$ExpectedBranch'. Actueel: '$currentBranch'. Start de runner vanuit de juiste repositorymap."
  }

  if (-not $SkipDockerBuild) {
    if ($FrontendPort -ne 5174 -or $BackendPort -ne 8011) {
      throw "Docker build/start via deze runner ondersteunt alleen de standaardpoorten 5174/8011. Start een geïsoleerde omgeving vooraf en gebruik -SkipDockerBuild met -FrontendPort en -BackendPort."
    }

    Write-Host "`n=== Docker build/start ===" -ForegroundColor Cyan
    docker compose up -d --build
  }

  Write-Host "`n=== Backend health ===" -ForegroundColor Cyan
  $healthOk = $false
  for ($i = 1; $i -le 12; $i++) {
    try {
      Write-Host "Healthcheck poging $i..."
      Invoke-RestMethod "$backendBaseUrl/api/health" | Out-Host
      $healthOk = $true
      break
    } catch {
      Write-Host "Backend nog niet bereikbaar: $($_.Exception.Message)"
      Start-Sleep -Seconds 10
    }
  }

  if (-not $healthOk) {
    throw "Backend healthcheck niet groen na 12 pogingen op $backendBaseUrl."
  }

  Invoke-RegressionFixtureCleanup

  Write-Host "`n=== Playwright frontend regressie via Docker ===" -ForegroundColor Cyan

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
    "tests/e2e/article-detail.frontend-regression.spec.js"
  ) -join " "

  docker run --rm `
    --add-host=host.docker.internal:host-gateway `
    -e PLAYWRIGHT_BASE_URL=$playwrightFrontendUrl `
    -e PLAYWRIGHT_API_URL=$playwrightBackendUrl `
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
    Invoke-RegressionFixtureCleanup
  } catch {
    Write-Host "Regression fixture cleanup na test faalde: $($_.Exception.Message)" -ForegroundColor Red
    if ($LASTEXITCODE -eq 0) {
      $global:LASTEXITCODE = 1
    }
  }
  Pop-Location
}
