$ErrorActionPreference = 'Stop'

$path = 'frontend\src\features\admin\lib\layer2RouteRunner.js'
if (!(Test-Path $path)) {
  throw "layer2RouteRunner.js niet gevonden: $path"
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = "$path.R9-06C_backup_$timestamp"
Copy-Item $path $backupPath -Force
Write-Host "Backup gemaakt: $backupPath"

$content = Get-Content $path -Raw -Encoding UTF8

# Share-import redirect mag geen technische parserstatus meer doorgeven.
$content = $content.Replace(
"  const parseStatus = encodeURIComponent(String(payload?.parse_status || importedReceipt?.parse_status || 'partial'))`r`n  const duplicateFlag = payload?.duplicate ? '1' : '0'`r`n  await navigateFrame(frame, `/kassa?share_status=success&receipt_table_id=`${encodeURIComponent(String(importedReceipt?.receipt_table_id || ''))}&duplicate=`${duplicateFlag}&parse_status=`${parseStatus}`)`r`n",
"  const statusLabel = encodeURIComponent(String(payload?.po_norm_status_label || importedReceipt?.po_norm_status_label || 'Controle nodig'))`r`n  const duplicateFlag = payload?.duplicate ? '1' : '0'`r`n  await navigateFrame(frame, `/kassa?share_status=success&receipt_table_id=`${encodeURIComponent(String(importedReceipt?.receipt_table_id || ''))}&duplicate=`${duplicateFlag}&po_norm_status_label=`${statusLabel}`)`r`n"
)

# Legacy fixture-key review_needed is functioneel nog de controle-nodig fixture.
# Hernoem alleen de regressietoolingvariabelen/fixture keys naar controlNeeded.
$content = $content.Replace('review_needed', 'controlNeeded')
$content = $content.Replace('reviewNeeded', 'controlNeeded')
$content = $content.Replace('ReviewNeeded', 'ControlNeeded')

[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
$content = Get-Content $path -Raw -Encoding UTF8

$forbidden = @('parse_status', 'review_needed')
foreach ($token in $forbidden) {
  if ($content.Contains($token)) {
    throw "R9-06C controle mislukt; token blijft aanwezig in regression runner: $token"
  }
}

$required = @('po_norm_status_label', 'Controle nodig', 'controlNeeded')
foreach ($marker in $required) {
  if (!$content.Contains($marker)) {
    throw "R9-06C controle mislukt; marker ontbreekt: $marker"
  }
  Write-Host "OK: $marker"
}

Write-Host 'R9-06C regression status-governance patch toegepast.'
Write-Host ''
Write-Host 'Volgende commando''s:'
Write-Host 'python .\tools\R9-06_receipt_status_governance_check.py "http://localhost:8011/api/receipts?householdId=1" "rezzerv-dev-token::admin@rezzerv.local"'
Write-Host 'npm --prefix frontend run build'
Write-Host 'git add frontend\src\features\admin\lib\layer2RouteRunner.js tools\R9-06C_align_regression_status_governance.ps1 tools\R9-06_receipt_status_governance_check.py'
Write-Host 'git commit -m "R9-06C Align regression tooling with receipt status governance"'
Write-Host 'git push'
