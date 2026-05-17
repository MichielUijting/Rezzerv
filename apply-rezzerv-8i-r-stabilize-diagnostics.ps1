$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8I-R stabilisatie tijdelijke diagnose-endpoints starten...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/main.py'
if (-not (Test-Path $path)) { throw "Bestand niet gevonden: $path" }

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

$markers = @(
    '/api/testing/receipt-filter-selftest',
    '/api/testing/receipt-line-flow-trace',
    '/api/testing/receipt-table-schema',
    '/api/testing/reset-active-receipt-testset'
)

# Verwijder standalone importregels die alleen voor tijdelijke endpoints waren toegevoegd.
$temporaryImports = @(
    'from app.services.receipt_service import _looks_like_false_article_metadata_line',
    'from app.services.receipt_service import _extract_receipt_lines',
    'from app.services.receipt_service import _extract_sparse_receipt_lines',
    'from app.services.receipt_service import _filter_non_product_receipt_lines',
    'from app.services.receipt_service import _should_skip_receipt_line',
    'from app.services.receipt_service import _looks_like_non_product_receipt_label'
)
foreach ($importLine in $temporaryImports) {
    $content = $content.Replace($importLine + "`r`n", '')
    $content = $content.Replace($importLine + "`n", '')
}

# Verwijder volledige endpoint-blokken op basis van decorators.
$patterns = @(
    '(?s)\r?\n\r?\n@app\.get\("/api/testing/receipt-filter-selftest"\).*?(?=\r?\n\r?\n@app\.|\r?\nfrom app\.api\.router import api_router|\z)',
    '(?s)\r?\n\r?\n@app\.get\("/api/testing/receipt-line-flow-trace"\).*?(?=\r?\n\r?\n@app\.|\r?\nfrom app\.api\.router import api_router|\z)',
    '(?s)\r?\n\r?\n@app\.get\("/api/testing/receipt-table-schema"\).*?(?=\r?\n\r?\n@app\.|\r?\nfrom app\.api\.router import api_router|\z)',
    '(?s)\r?\n\r?\n@app\.post\("/api/testing/reset-active-receipt-testset"\).*?(?=\r?\n\r?\n@app\.|\r?\nfrom app\.api\.router import api_router|\z)'
)
foreach ($pattern in $patterns) {
    $content = [regex]::Replace($content, $pattern, "`r`n")
}

# Extra veiligheidscheck: als marker nog bestaat, stoppen zonder weg te schrijven.
foreach ($marker in $markers) {
    if ($content.Contains($marker)) {
        throw "Cleanup niet volledig: marker nog aanwezig: $marker"
    }
}

if ($content -ne $original) {
    Copy-Item $path "$path.8i-r-stabilize-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Tijdelijke diagnose/reset-endpoints verwijderd uit main.py.' -ForegroundColor Green
} else {
    Write-Host 'Geen tijdelijke endpoints gevonden in main.py; niets gewijzigd.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Belangrijk:' -ForegroundColor Yellow
Write-Host '- Parserfilter 8I-1A blijft ongemoeid.'
Write-Host '- Geen databasewijziging uitgevoerd.'
Write-Host '- Geen reset uitgevoerd.'
Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
