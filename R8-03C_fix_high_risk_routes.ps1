# R8-03C corrective patch — remove remaining HIGH-risk dev route decorators from backend\app\main.py
# Run from: C:\Users\Gebruiker\Rezzerv_Github

$ErrorActionPreference = "Stop"

$mainPath = "backend\app\main.py"

if (!(Test-Path $mainPath)) {
    throw "Niet gevonden: $mainPath. Start dit script vanuit C:\Users\Gebruiker\Rezzerv_Github"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = "$mainPath.R8-03C_highrisk_backup_$timestamp"
Copy-Item $mainPath $backupPath -Force

$targets = @(
    '@app.post("/api/dev/reset-data")',
    '@app.post("/api/dev/generate-demo-data")',
    '@app.post("/api/dev/generate-large-dataset")',
    '@app.post("/api/dev/regression/reset")',
    '@app.post("/api/dev/regression/cleanup")'
)

$lines = Get-Content $mainPath
$removed = @()
$newLines = foreach ($line in $lines) {
    if ($targets -contains $line.Trim()) {
        $removed += $line.Trim()
        continue
    }
    $line
}

Set-Content -Path $mainPath -Value $newLines -Encoding UTF8

Write-Host ""
Write-Host "Backup gemaakt:" $backupPath
Write-Host "Verwijderde decorators:"
$removed | ForEach-Object { Write-Host " - $_" }

Write-Host ""
Write-Host "Controle resterende exacte high-risk decorators:"
$remaining = Select-String -Path $mainPath -SimpleMatch -Pattern $targets
if ($remaining) {
    Write-Host "NIET GOED: er staan nog high-risk route decorators in main.py:" -ForegroundColor Red
    $remaining | ForEach-Object { Write-Host ("{0}:{1}: {2}" -f $_.Path, $_.LineNumber, $_.Line) }
    exit 1
}

Write-Host "OK: alle vijf high-risk route decorators zijn uit main.py verwijderd." -ForegroundColor Green

Write-Host ""
Write-Host "Volgende commando's:"
Write-Host 'git diff -- backend\app\main.py'
Write-Host 'git add backend\app\main.py'
Write-Host 'git commit -m "R8-03C Remove remaining high-risk dev routes"'
Write-Host 'git push'
