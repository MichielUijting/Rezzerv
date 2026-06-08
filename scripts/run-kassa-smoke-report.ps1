param(
  [string]$BaseUrl = "http://127.0.0.1:8011",
  [int]$TimeoutSeconds = 180,
  [int]$PollSeconds = 5,
  [switch]$ShowProgress
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "Kassa smoke-test starten..." -ForegroundColor Cyan

$run = Invoke-RestMethod `
  -Method Post `
  -Uri "$BaseUrl/api/admin/kassa-smoke/run" `
  -ContentType "application/json" `
  -Body "{}"

$jobId = $run.job_id
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$status = $null
$lastMessage = ""

while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds $PollSeconds

  $status = Invoke-RestMethod `
    -Method Get `
    -Uri "$BaseUrl/api/admin/kassa-smoke/status"

  $lastMessage = $status.message

  if ($status.status -notin @("running", "queued", "starting")) {
    break
  }

  if ($ShowProgress) {
    Write-Host "Smoke-test loopt nog: $($status.message)"
  }
}

if (-not $status) {
  Write-Host ""
  Write-Host "KASSA SMOKE RAPPORT" -ForegroundColor Red
  Write-Host "Status: GEEN STATUS ONTVANGEN"
  exit 1
}

if ($status.status -in @("running", "queued", "starting")) {
  Write-Host ""
  Write-Host "KASSA SMOKE RAPPORT" -ForegroundColor Red
  Write-Host "Status: TIMEOUT"
  Write-Host "Job: $jobId"
  Write-Host "Laatste melding: $lastMessage"
  exit 1
}

$report = $status.report
$summary = $report.summary

Write-Host ""
Write-Host "KASSA SMOKE RAPPORT" -ForegroundColor Cyan
Write-Host "Job: $jobId"
Write-Host "Status: $($status.status)"
Write-Host "Melding: $($status.message)"

if ($summary) {
  Write-Host ""
  Write-Host "Samenvatting:"
  Write-Host "Getest:      $($summary.tested_receipt_count)"
  Write-Host "Geslaagd:    $($summary.passed_count)"
  Write-Host "Gefaald:     $($summary.failed_count)"
  Write-Host "Geblokkeerd: $($summary.blocked_count)"
}

if ($report.chains) {
  Write-Host ""
  Write-Host "Ketens:"
  foreach ($chain in $report.chains) {
    $name = $chain.store_chain
    if (-not $name) { $name = $chain.chain }
    if (-not $name) { $name = $chain.name }

    $chainStatus = $chain.status
    if (-not $chainStatus) { $chainStatus = "onbekend" }

    Write-Host "- ${name}: ${chainStatus}"
  }
}

if ($report.blocking_issues -and $report.blocking_issues.Count -gt 0) {
  Write-Host ""
  Write-Host "Blokkades:" -ForegroundColor Yellow
  foreach ($issue in $report.blocking_issues) {
    Write-Host "- $issue"
  }
}

if ($report.results) {
  $failed = @($report.results | Where-Object { $_.status -notin @("passed", "success") })
  if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Niet-groene cases:" -ForegroundColor Yellow
    foreach ($case in $failed) {
      Write-Host "- $($case.case_id): $($case.status)"
    }
  }
}

$failedCount = 0
$blockedCount = 0

if ($summary) {
  if ($null -ne $summary.failed_count) { $failedCount = [int]$summary.failed_count }
  if ($null -ne $summary.blocked_count) { $blockedCount = [int]$summary.blocked_count }
}

$passed =
  $status.status -in @("passed", "completed", "success") -and
  $failedCount -eq 0 -and
  $blockedCount -eq 0

if ($passed) {
  Write-Host ""
  Write-Host "Kassa smoke-test: PASSED" -ForegroundColor Green
  exit 0
}

Write-Host ""
Write-Host "Kassa smoke-test: NIET GROEN" -ForegroundColor Red
exit 1
