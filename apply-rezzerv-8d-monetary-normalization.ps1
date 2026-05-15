$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8D monetary-normalization hotfix starten...' -ForegroundColor Cyan

$receiptServicePath = Join-Path $root 'backend/app/services/receipt_service.py'
if (-not (Test-Path $receiptServicePath)) {
    throw "Bestand niet gevonden: $receiptServicePath"
}

$service = Get-Content $receiptServicePath -Raw

# Fix 1: discount_total is in Rezzerv als negatief bedrag opgeslagen.
# De veilige nettosom is dus line_sum + discount_total, niet line_sum - discount_total.
$service = $service -replace 'net_line_sum = line_sum - Decimal\(str\(discount_total or 0\)\)', 'net_line_sum = line_sum + Decimal(str(discount_total or 0))'

# Fix 2: wanneer de nettosom veilig op het totaal aansluit, mag de bestaande parserflow approved opslaan.
# Dit is geen SSOT-omzeiling: alleen bestaande parseroutput wordt strenger financieel gevalideerd.
$service = $service -replace "if diff <= Decimal\('0\.25'\):\s*\r?\n\s*return 'parsed'", "if diff <= Decimal('0.25'):`r`n            return 'approved'"

# Fix 3: als regels en totaal niet veilig aansluiten, niet automatisch parsed opslaan.
$service = $service -replace "# Essentiële kopgegevens zijn aanwezig; artikelregels kunnen later handmatig\s*\r?\n\s*# worden verbeterd zonder dat de hele bon in de controlebak hoeft te blijven\.\s*\r?\n\s*return 'parsed'", "# Essentiële kopgegevens zijn aanwezig, maar de financiële controle sluit niet veilig.`r`n    return 'review_needed'"

Set-Content $receiptServicePath $service -Encoding UTF8

$kpiPath = Join-Path $root 'backend/receipt_ingestion/kassa_active_scope_kpi.py'
if (Test-Path $kpiPath) {
    $kpi = Get-Content $kpiPath -Raw

    # Voeg discount_total zichtbaar toe aan de KPI-query/output zonder status te schrijven.
    $kpi = $kpi -replace "'line_sum': row.get\('active_line_sum'\),\s*\r?\n\s*'line_sum_matches_total': _amount_equals\(row.get\('total_amount'\), row.get\('active_line_sum'\)\),", "'line_sum': _amount_to_float((_to_decimal(row.get('active_line_sum')) or Decimal('0.00')) + (_to_decimal(row.get('discount_total')) or Decimal('0.00'))),`r`n            'gross_line_sum': row.get('active_line_sum'),`r`n            'discount_total': row.get('discount_total'),`r`n            'line_sum_matches_total': _amount_equals(row.get('total_amount'), ((_to_decimal(row.get('active_line_sum')) or Decimal('0.00')) + (_to_decimal(row.get('discount_total')) or Decimal('0.00')))),"

    if ($kpi -notmatch 'def _amount_to_float') {
        $kpi = $kpi + "`r`n`r`ndef _amount_to_float(value):`r`n    return float(value) if value is not None else None`r`n"
    }

    Set-Content $kpiPath $kpi -Encoding UTF8
}

Write-Host ''
Write-Host '8D monetary-normalization hotfix toegepast.' -ForegroundColor Green
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host ''
Write-Host 'Let op: bestaande bonnen moeten daarna opnieuw worden geparsed om DB-statussen te wijzigen.' -ForegroundColor Yellow
