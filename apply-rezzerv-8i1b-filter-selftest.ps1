$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8I-1B filter-selftest patch starten...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/main.py'
if (-not (Test-Path $path)) {
    throw "Bestand niet gevonden: $path"
}

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

if ($content -notmatch 'receipt-filter-selftest') {

$importAnchor = 'from app.services.receipt_service import ('
if ($content.Contains($importAnchor) -and $content -notmatch '_looks_like_false_article_metadata_line') {
    $content = $content.Replace(
        'from app.services.receipt_service import (',
        "from app.services.receipt_service import (`r`n    _looks_like_false_article_metadata_line,"
    )
}

$endpoint = @'


@app.get("/api/testing/receipt-filter-selftest")
def receipt_filter_selftest():
    test_inputs = [
        "ZON 10.00",
        "ZA 8.00",
        "ZO 12.00",
        "B 9,00% 6,01 0,54",
        "B 9,00% 4,59 0,41",
        "Maandag t/m Woernsdag",
        "50.89",
        "99 ,64 23,92 4,92",
        "26 11:01 I08335 175 zege1s +",
    ]

    results = []

    for value in test_inputs:
        matched_reason = None
        lowered = value.lower()

        if any(day in lowered for day in ['maandag', 'dinsdag', 'woensdag', 'woernsdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag']):
            matched_reason = 'weekday_or_action_period'
        elif any(day in lowered.split()[:1] for day in ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo', 'zon']):
            matched_reason = 'opening_hours'
        elif lowered.startswith('b ') and '%' in lowered:
            matched_reason = 'vat_summary'
        elif 'zegel' in lowered or 'zege1s' in lowered or 'pluspunten' in lowered:
            matched_reason = 'loyalty_noise'
        elif value.replace('.', '').replace(',', '').replace(' ', '').isdigit():
            matched_reason = 'numeric_noise'

        results.append({
            'input': value,
            'expected_filtered': True,
            'actual_filtered': bool(_looks_like_false_article_metadata_line(value)),
            'matched_reason': matched_reason,
        })

    return {
        'success': True,
        'results': results,
    }
'@

$content += $endpoint
}

if ($content -ne $original) {
    Copy-Item $path "$path.8i1b-selftest-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Filter-selftest endpoint toegevoegd.' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast; endpoint lijkt al aanwezig.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna Swagger openen en GET /api/testing/receipt-filter-selftest uitvoeren.' -ForegroundColor Yellow
