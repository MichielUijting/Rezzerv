param()

CLS

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== Huishouden-0 contractscan ===" -ForegroundColor Cyan

$scanTargets = @(
  (Join-Path $repoRoot "frontend\tests")
  (Join-Path $repoRoot "backend\tests")
  (Join-Path $repoRoot "scripts")
)

$extensions = @(".js", ".jsx", ".ts", ".tsx", ".py", ".ps1", ".json", ".md")
$excludedFiles = @(
  (Join-Path $repoRoot "scripts\assert-household-zero-test-contract.ps1")
)

$forbiddenTestPatterns = @(
  @{ Name = "hardcoded household_id 1"; Pattern = '(?i)household[_-]?id\s*[:=]\s*["'']?1\b' },
  @{ Name = "hardcoded householdId 1"; Pattern = '(?i)householdId\s*[:=]\s*["'']?1\b' },
  @{ Name = "Playwright huishouden 1"; Pattern = '(?i)PLAYWRIGHT_HOUSEHOLD_ID\s*=\s*["'']?1\b' },
  @{ Name = "demo huishouden 1"; Pattern = '(?i)DEMO_HOUSEHOLD_ID\s*=\s*["'']1["'']' },
  @{ Name = "fallback naar huishouden 1"; Pattern = '(?i)active_household_id\s*\|\|\s*["'']1["'']' },
  @{ Name = "legacy regressieaccount"; Pattern = '(?i)admin@rezzerv\.local' }
)

$violations = New-Object System.Collections.Generic.List[object]

foreach ($target in $scanTargets) {
  if (-not (Test-Path $target)) {
    continue
  }

  $files = Get-ChildItem -Path $target -Recurse -File | Where-Object {
    $extensions -contains $_.Extension.ToLowerInvariant() -and
    $excludedFiles -notcontains $_.FullName
  }

  foreach ($file in $files) {
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
}

$frontendSource = Join-Path $repoRoot "frontend\src"
if (Test-Path $frontendSource) {
  $frontendFiles = Get-ChildItem -Path $frontendSource -Recurse -File | Where-Object {
    @(".js", ".jsx", ".ts", ".tsx") -contains $_.Extension.ToLowerInvariant()
  }

  $legacyPriorityPattern = '(?i)\.id\s*\|\|[^\r\n;]{0,160}active_household_id'
  $hardcodedArticleGroupPattern = '(?i)/api/article-groups\?household_id=1\b'

  foreach ($file in $frontendFiles) {
    foreach ($rule in @(
      @{ Name = "legacy id vóór active_household_id"; Pattern = $legacyPriorityPattern },
      @{ Name = "artikelgroepen hardcoded huishouden 1"; Pattern = $hardcodedArticleGroupPattern }
    )) {
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
