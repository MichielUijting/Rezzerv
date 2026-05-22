$ErrorActionPreference = 'Stop'

$mainPath = 'backend\app\main.py'
if (!(Test-Path $mainPath)) {
  throw "main.py niet gevonden op $mainPath"
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = "$mainPath.R8-04B_alias_backup_$timestamp"
Copy-Item $mainPath $backupPath -Force
Write-Host "Backup gemaakt: $backupPath"

$content = Get-Content $mainPath -Raw -Encoding UTF8

$aliases = @(
  @{ Old='@app.get("/api/dev/article-history")'; New='@app.get("/api/testing/diagnostics/article-history")' },
  @{ Old='@app.post("/api/dev/browser-regression/reset-fixture")'; New='@app.post("/api/testing/fixtures/browser-regression/reset")' },
  @{ Old='@app.post("/api/dev/diagnostics/store-location-options")'; New='@app.post("/api/testing/diagnostics/store-location-options")' },
  @{ Old='@app.get("/api/dev/diagnostics/store-process-validation")'; New='@app.get("/api/testing/diagnostics/store-process-validation")' },
  @{ Old='@app.get("/api/dev/export-receipt-export-fixture")'; New='@app.get("/api/testing/fixtures/receipt-export/download")' },
  @{ Old='@app.post("/api/dev/generate-layer1-receipt-fixture")'; New='@app.post("/api/testing/fixtures/receipt-layer1/generate")' },
  @{ Old='@app.post("/api/dev/generate-receipt-export-fixture")'; New='@app.post("/api/testing/fixtures/receipt-export/generate")' },
  @{ Old='@app.get("/api/dev/inventory-preview")'; New='@app.get("/api/testing/diagnostics/inventory-preview")' },
  @{ Old='@app.get("/api/dev/purchase-import-batches/{batch_id}/diagnostics")'; New='@app.get("/api/testing/diagnostics/purchase-import-batches/{batch_id}")' },
  @{ Old='@app.post("/api/dev/regression/almost-out-prediction")'; New='@app.post("/api/testing/regression/almost-out-prediction")' },
  @{ Old='@app.post("/api/dev/regression/almost-out-self-test")'; New='@app.post("/api/testing/regression/almost-out-self-test")' },
  @{ Old='@app.post("/api/dev/regression/ensure-inventory-fixture")'; New='@app.post("/api/testing/fixtures/inventory/ensure")' },
  @{ Old='@app.get("/api/dev/regression/receipt-fixture-file")'; New='@app.get("/api/testing/fixtures/receipt/file")' },
  @{ Old='@app.post("/api/dev/regression/seed-kassa-receipts")'; New='@app.post("/api/testing/fixtures/receipts/seed-kassa")' },
  @{ Old='@app.post("/api/dev/run-layer1-tests")'; New='@app.post("/api/testing/regression/layer1/run")' },
  @{ Old='@app.post("/api/dev/run-layer2-tests")'; New='@app.post("/api/testing/regression/layer2/run")' },
  @{ Old='@app.post("/api/dev/run-layer3-tests")'; New='@app.post("/api/testing/regression/layer3/run")' },
  @{ Old='@app.post("/api/dev/run-parsing-fixture-tests")'; New='@app.post("/api/testing/regression/parsing-fixtures/run")' },
  @{ Old='@app.post("/api/dev/run-parsing-raw-tests")'; New='@app.post("/api/testing/regression/parsing-raw/run")' },
  @{ Old='@app.post("/api/dev/run-regression-tests")'; New='@app.post("/api/testing/regression/all/run")' },
  @{ Old='@app.post("/api/dev/run-smoke-tests")'; New='@app.post("/api/testing/regression/smoke/run")' },
  @{ Old='@app.get("/api/dev/status")'; New='@app.get("/api/testing/status")' },
  @{ Old='@app.post("/api/dev/test-report")'; New='@app.post("/api/testing/reports/complete")' },
  @{ Old='@app.get("/api/dev/test-report/latest")'; New='@app.get("/api/testing/reports/latest")' },
  @{ Old='@app.get("/api/dev/test-status")'; New='@app.get("/api/testing/status")' }
)

$added = @()
$skippedExisting = @()
$missing = @()

foreach ($alias in $aliases) {
  if ($content.Contains($alias.New)) {
    $skippedExisting += $alias.New
    continue
  }
  if (!$content.Contains($alias.Old)) {
    $missing += $alias.Old
    continue
  }
  $content = $content.Replace($alias.Old, "$($alias.New)`r`n$($alias.Old)")
  $added += $alias.New
}

[System.IO.File]::WriteAllText($mainPath, $content, [System.Text.UTF8Encoding]::new($false))

Write-Host "Toegevoegde TEST-aliases: $($added.Count)"
foreach ($item in $added) { Write-Host " + $item" }

if ($skippedExisting.Count -gt 0) {
  Write-Host "Al aanwezig: $($skippedExisting.Count)"
}

if ($missing.Count -gt 0) {
  Write-Host "Niet gevonden oude decorators: $($missing.Count)"
  foreach ($item in $missing) { Write-Host " ! $item" }
  throw "Niet alle oude DEV-decorators zijn gevonden; controleer main.py voordat je commit."
}

Write-Host "Controle nieuwe /api/testing aliases:"
$check = Select-String -Path $mainPath -Pattern '/api/testing/'
Write-Host "Aantal /api/testing vermeldingen in main.py: $($check.Count)"
Write-Host "Volgende commando's:"
Write-Host "git diff -- backend\app\main.py"
Write-Host "git add backend\app\main.py tools\R8-04B_add_testing_aliases.ps1 docs\R8-04A-dev-to-testing-migratieplan.md"
Write-Host "git commit -m \"R8-04B Add testing aliases for remaining dev routes\""
Write-Host "git push"
