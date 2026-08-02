param()

CLS

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== Huishouden-0 contractscan ===" -ForegroundColor Cyan

# Alleen bestanden die onderdeel zijn van de centrale frontendregressie,
# de huishouden-0 fixtureketen of de aansluitende productie-ketentest.
# Losse unit- en beveiligingstests mogen bewust andere huishoudens modelleren.
$canonicalRelativeFiles = @(
  "scripts\run-frontend-regression-report.ps1",
  "scripts\run-receipt-inventory-chain.ps1",
  "backend\tests\authorization_role_matrix_selftest.py",
  "backend\tests\household_zero_regression_fixture.py",
  "frontend\tests\e2e\auth.setup.js",
  "frontend\tests\e2e\helpers\devApi.js",
  "frontend\tests\e2e\kassa.frontend-regression.spec.js",
  "frontend\tests\e2e\uitpakken.frontend-regression.spec.js",
  "frontend\tests\e2e\external-databases.frontend-regression.spec.js",
  "frontend\tests\e2e\external-databases-off.frontend-regression.spec.js",
  "frontend\tests\e2e\external-databases-unlink.frontend-regression.spec.js",
  "frontend\tests\e2e\external-databases-known-gtin.frontend-regression.spec.js",
  "frontend\tests\e2e\external-databases-no-redundant-buttons.frontend-regression.spec.js",
  "frontend\tests\e2e\product-groups.frontend-regression.spec.js",
  "frontend\tests\e2e\settings-article-groups.frontend-regression.spec.js",
  "frontend\tests\e2e\article-detail.frontend-regression.spec.js",
  "frontend\tests\e2e\catalog-gpc-search.frontend-regression.spec.js"
)

$canonicalFiles = foreach ($relativePath in $canonicalRelativeFiles) {
  $fullPath = Join-Path $repoRoot $relativePath
  if (Test-Path $fullPath -PathType Leaf) {
    Get-Item $fullPath
  }
}

$forbiddenTestPatterns = @(
  @{ Name = "hardcoded household_id 1"; Pattern = '(?i)household[_-]?id\s*[:=]\s*["'']?1\b' },
  @{ Name = "hardcoded householdId 1"; Pattern = '(?i)householdId\s*[:=]\s*["'']?1\b' },
  @{ Name = "Playwright huishouden 1"; Pattern = '(?i)PLAYWRIGHT_HOUSEHOLD_ID\s*=\s*["'']?1\b' },
  @{ Name = "demo huishouden 1"; Pattern = '(?i)DEMO_HOUSEHOLD_ID\s*=\s*["'']1["'']' },
  @{ Name = "fallback naar huishouden 1"; Pattern = '(?i)active_household_id\s*\|\|\s*["'']1["'']' },
  @{ Name = "legacy regressieaccount"; Pattern = '(?i)(?<![A-Za-z0-9._%+\-])admin@rezzerv\.local(?![A-Za-z0-9.\-])' }
)

$violations = New-Object System.Collections.Generic.List[object]

foreach ($file in $canonicalFiles) {
  foreach ($rule in $forbiddenTestPatterns) {
    $matches = Select-String -Path $file.FullName -Pattern $rule.Pattern -AllMatches
    foreach ($match in $matches) {
      $violations.Add([pscustomobject]@{
        Rule = $rule.Name
        File = $file.FullName.Substring($repoRoot.Length + 1)
        Line = $match.LineNumber
        Text = $match.Line.Trim()
      })
    }
  }
}

# Relevante productie-frontendcode wordt apart bewaakt op fouten waarbij
# huishouden 0 als falsy waarde verloren kan gaan of legacy household.id
# voorrang krijgt boven de actieve server-side sessie.
$frontendSource = Join-Path $repoRoot "frontend\src"
if (Test-Path $frontendSource) {
  $frontendFiles = Get-ChildItem -Path $frontendSource -Recurse -File | Where-Object {
    @(".js", ".jsx", ".ts", ".tsx") -contains $_.Extension.ToLowerInvariant()
  }

  $frontendRules = @(
    @{ Name = "legacy id voor active_household_id"; Pattern = '(?i)\.id\s*\|\|[^\r\n;]{0,160}active_household_id' },
    @{ Name = "active_household_id gebruikt falsy fallback"; Pattern = '(?i)active_household_id\s*\|\|' },
    @{ Name = "artikelgroepen hardcoded huishouden 1"; Pattern = '(?i)/api/article-groups\?household_id=1\b' }
  )

  foreach ($file in $frontendFiles) {
    foreach ($rule in $frontendRules) {
      $matches = Select-String -Path $file.FullName -Pattern $rule.Pattern -AllMatches
      foreach ($match in $matches) {
        $violations.Add([pscustomobject]@{
          Rule = $rule.Name
          File = $file.FullName.Substring($repoRoot.Length + 1)
          Line = $match.LineNumber
          Text = $match.Line.Trim()
        })
      }
    }
  }
}

if ($violations.Count -gt 0) {
  Write-Host "HOUSEHOLD_ZERO_CONTRACT_SCAN=FAIL" -ForegroundColor Red
  $violations |
    Sort-Object File, Line, Rule |
    Format-Table Rule, File, Line, Text -AutoSize |
    Out-Host
  throw "Huishouden-0-contract geschonden: $($violations.Count) verboden verwijzing(en) gevonden."
}

Write-Host "HOUSEHOLD_ZERO_CONTRACT_SCAN=PASS" -ForegroundColor Green
