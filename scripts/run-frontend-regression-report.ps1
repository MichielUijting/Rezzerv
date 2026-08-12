param(
  [switch]$SkipDockerBuild
)

CLS

$ErrorActionPreference = "Stop"

Write-Host "=== Rezzerv centrale frontendregressie ===" -ForegroundColor Cyan

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

$fixturesPrepared = $false
$runFailed = $false
$promptedSuperuserPassword = $false
$superuserPasswordBstr = [IntPtr]::Zero

$superuserEmail = if ($env:REZZERV_REGRESSION_SUPERUSER_EMAIL) {
  $env:REZZERV_REGRESSION_SUPERUSER_EMAIL
} else {
  "supergebruiker@rezzerv.local"
}

$superuserPassword = $env:REZZERV_REGRESSION_SUPERUSER_PASSWORD
$testAdminEmail = "test-admin@rezzerv.local"
$testAdminPassword = "Rt$([Guid]::NewGuid().ToString('N'))"

if (-not $superuserPassword) {
  Write-Host "`n=== Vereist PO-credential ===" -ForegroundColor Cyan
  Write-Host "Deze regressierun heeft het wachtwoord van de platform-superuser nodig." -ForegroundColor Yellow
  $secureSuperuserPassword = Read-Host "Voer het wachtwoord van $superuserEmail in" -AsSecureString
  $superuserPasswordBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSuperuserPassword)
  $superuserPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($superuserPasswordBstr)
  $env:REZZERV_REGRESSION_SUPERUSER_PASSWORD = $superuserPassword
  $promptedSuperuserPassword = $true
}

try {
  Write-Host "`n=== Huishouden-0 contractscan ===" -ForegroundColor Cyan
  try {
    & (Join-Path $PSScriptRoot "assert-household-zero-test-contract.ps1")
  }
  catch {
    throw "Huishouden-0-contractscan is gefaald: $($_.Exception.Message)"
  }

  if (-not $SkipDockerBuild) {
    Write-Host "`n=== Docker build/start ===" -ForegroundColor Cyan
    docker compose up -d --build
    $dockerBuildExitCode = $LASTEXITCODE
    if ($dockerBuildExitCode -ne 0) { throw "Docker build/start is gefaald met exitcode $dockerBuildExitCode." }
    Write-Host "`n=== Stabilisatie na hernieuwde opbouw: 90 seconden ===" -ForegroundColor Cyan
    Start-Sleep -Seconds 90
  }

  Write-Host "`n=== Backend health ===" -ForegroundColor Cyan
  $healthOk = $false
  for ($i = 1; $i -le 12; $i++) {
    try {
      Write-Host "Healthcheck poging $i..."
      Invoke-RestMethod http://localhost:8011/api/health | Out-Host
      $healthOk = $true
      break
    }
    catch {
      Write-Host "Backend nog niet bereikbaar: $($_.Exception.Message)"
      Start-Sleep -Seconds 10
    }
  }
  if (-not $healthOk) { throw "Backend healthcheck niet groen na 12 pogingen." }

  Write-Host "`n=== Autorisatiematrix server-side sessies ===" -ForegroundColor Cyan
  docker compose exec -T `
    -e REZZERV_TEST_SUPERUSER_EMAIL=$superuserEmail `
    -e REZZERV_TEST_SUPERUSER_PASSWORD=$superuserPassword `
    -e REZZERV_TEST_ADMIN_EMAIL=$testAdminEmail `
    -e REZZERV_TEST_ADMIN_PASSWORD=$testAdminPassword `
    backend python /app/tests/authorization_role_matrix_selftest.py
  if ($LASTEXITCODE -ne 0) { throw "Autorisatiematrix-selftest is gefaald met exitcode $LASTEXITCODE." }

  Write-Host "`n=== Winkelen Release 1 backend-selftest ===" -ForegroundColor Cyan
  docker compose exec -T -e PYTHONPATH=/app backend python /app/tests/shopping_list_release1_selftest.py
  if ($LASTEXITCODE -ne 0) { throw "Winkelen Release 1 backend-selftest is gefaald met exitcode $LASTEXITCODE." }

  Write-Host "`n=== Huishouden-0 regressie-fixtures voorbereiden ===" -ForegroundColor Cyan
  docker compose exec -T backend python /app/tests/household_zero_regression_fixture.py prepare
  if ($LASTEXITCODE -ne 0) { throw "Voorbereiden van huishouden-0-fixtures is gefaald met exitcode $LASTEXITCODE." }
  $fixturesPrepared = $true

  Write-Host "`n=== Playwright frontend regressie via Docker ===" -ForegroundColor Cyan
  Write-Host "Platform-superuser: $superuserEmail; huishouden: 0" -ForegroundColor Cyan
  Write-Host "Playwright-testaccount: $testAdminEmail; huishouden: 0" -ForegroundColor Cyan

  $frontendPath = (Join-Path $repoRoot "frontend").Replace("\", "/")
  $parallelTestFiles = @(
    "tests/e2e/kassa.frontend-regression.spec.js",
    "tests/e2e/uitpakken.frontend-regression.spec.js",
    "tests/e2e/winkelen.frontend-regression.spec.js",
    "tests/e2e/meldingen.frontend-regression.spec.js",
    "tests/e2e/superuser.frontend-regression.spec.js",
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
  $kassaImportTestFile = "tests/e2e/kassa-import-chain.frontend-regression.spec.js"

  Write-Host "`n=== Playwright fase 1/2: bestaande regressieset parallel ===" -ForegroundColor Cyan
  docker run --rm `
    --add-host=host.docker.internal:host-gateway `
    -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:5174 `
    -e PLAYWRIGHT_API_URL=http://host.docker.internal:8011 `
    -e PLAYWRIGHT_TEST_ADMIN_EMAIL=$testAdminEmail `
    -e PLAYWRIGHT_TEST_ADMIN_PASSWORD=$testAdminPassword `
    -e PLAYWRIGHT_HOUSEHOLD_ID=0 `
    -e PLAYWRIGHT_SUPERUSER_EMAIL=$superuserEmail `
    -e PLAYWRIGHT_SUPERUSER_PASSWORD=$superuserPassword `
    -v "${frontendPath}:/work" `
    -v rezzerv_playwright_node_modules:/work/node_modules `
    -w /work `
    mcr.microsoft.com/playwright:v1.58.2-noble `
    bash -lc "npm ci && ./node_modules/.bin/playwright test --workers=3 $parallelTestFiles"
  if ($LASTEXITCODE -ne 0) { throw "Playwright bestaande frontendregressie is gefaald met exitcode $LASTEXITCODE." }

  Write-Host "`n=== Playwright fase 2/2: echte Kassa-importketen geisoleerd ===" -ForegroundColor Cyan
  docker run --rm `
    --add-host=host.docker.internal:host-gateway `
    -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:5174 `
    -e PLAYWRIGHT_API_URL=http://host.docker.internal:8011 `
    -e PLAYWRIGHT_TEST_ADMIN_EMAIL=$testAdminEmail `
    -e PLAYWRIGHT_TEST_ADMIN_PASSWORD=$testAdminPassword `
    -e PLAYWRIGHT_HOUSEHOLD_ID=0 `
    -e PLAYWRIGHT_SUPERUSER_EMAIL=$superuserEmail `
    -e PLAYWRIGHT_SUPERUSER_PASSWORD=$superuserPassword `
    -v "${frontendPath}:/work" `
    -v rezzerv_playwright_node_modules:/work/node_modules `
    -w /work `
    mcr.microsoft.com/playwright:v1.58.2-noble `
    bash -lc "./node_modules/.bin/playwright test --workers=1 $kassaImportTestFile"
  if ($LASTEXITCODE -ne 0) { throw "Playwright Kassa-importregressie is gefaald met exitcode $LASTEXITCODE." }

  Write-Host "`n=== Frontend regressie groen: bestaande suite + geisoleerde Kassa-importketen ===" -ForegroundColor Green
}
catch {
  $runFailed = $true
  throw
}
finally {
  if ($fixturesPrepared) {
    try {
      Write-Host "`n=== Huishouden-0 regressie-fixtures opruimen ===" -ForegroundColor Cyan
      docker compose exec -T backend python /app/tests/household_zero_regression_fixture.py cleanup
      if ($LASTEXITCODE -ne 0) { throw "Cleanup gaf exitcode $LASTEXITCODE." }
    }
    catch {
      Write-Host "Regression fixture cleanup na test faalde: $($_.Exception.Message)" -ForegroundColor Red
      if (-not $runFailed) { throw }
    }
  }
  else {
    Write-Host "`n=== Fixture-cleanup overgeslagen: fixtures niet voorbereid ===" -ForegroundColor DarkGray
  }

  try {
    Write-Host "`n=== Playwright-testartefacten opruimen ===" -ForegroundColor Cyan
    $playwrightArtifacts = @(
      (Join-Path $repoRoot "frontend\playwright-report"),
      (Join-Path $repoRoot "frontend\playwright"),
      (Join-Path $repoRoot "frontend\test-results")
    )
    foreach ($artifactPath in $playwrightArtifacts) {
      if (Test-Path $artifactPath) {
        Remove-Item -Recurse -Force $artifactPath
        Write-Host "Verwijderd: $artifactPath" -ForegroundColor DarkGray
      }
    }
  }
  catch {
    Write-Host "Opruimen van Playwright-testartefacten faalde: $($_.Exception.Message)" -ForegroundColor Red
    if (-not $runFailed) { throw }
  }

  $testAdminPassword = $null
  $superuserPassword = $null
  if ($promptedSuperuserPassword) {
    Remove-Item Env:\REZZERV_REGRESSION_SUPERUSER_PASSWORD -ErrorAction SilentlyContinue
  }
  if ($superuserPasswordBstr -ne [IntPtr]::Zero) {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($superuserPasswordBstr)
  }
  Pop-Location
}