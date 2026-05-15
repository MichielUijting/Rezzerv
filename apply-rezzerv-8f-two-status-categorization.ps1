$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8F two-status receipt categorization starten...' -ForegroundColor Cyan

# 1. KPI: Handmatig en overige niet-goedgekeurde statussen tonen als Controle nodig.
$kpiPath = Join-Path $root 'backend/receipt_ingestion/kassa_active_scope_kpi.py'
if (Test-Path $kpiPath) {
    $kpi = Get-Content $kpiPath -Raw -Encoding UTF8
    $original = $kpi
    $kpi = $kpi.Replace("'manual': 'Handmatig',", "'manual': 'Controle nodig',")
    $kpi = $kpi.Replace("'failed': 'Niet herkend',", "'failed': 'Controle nodig',")
    $kpi = $kpi.Replace("'parsed': 'Geparsed',", "'parsed': 'Controle nodig',")
    $kpi = $kpi.Replace("'partial': 'Gedeeltelijk herkend',", "'partial': 'Controle nodig',")
    if ($kpi -ne $original) {
        Copy-Item $kpiPath "$kpiPath.8f-backup" -Force
        Set-Content $kpiPath $kpi -Encoding UTF8
        Write-Host 'KPI-statusmapping aangepast.' -ForegroundColor Green
    } else {
        Write-Host 'KPI-statusmapping was al aangepast of bestand wijkt af.' -ForegroundColor Yellow
    }
}

# 2. Backend service: parse_status manual normaliseren naar review_needed bij opslag/serialisatie waar tekstueel aanwezig.
$servicePath = Join-Path $root 'backend/app/services/receipt_service.py'
if (Test-Path $servicePath) {
    $service = Get-Content $servicePath -Raw -Encoding UTF8
    $original = $service

    # Alleen veilige tekstuele mappings: geen parserextractie wijzigen.
    $service = $service.Replace("'manual': 'Handmatig'", "'manual': 'Controle nodig'")
    $service = $service.Replace('"manual": "Handmatig"', '"manual": "Controle nodig"')
    $service = $service.Replace("parse_status = 'manual'", "parse_status = 'review_needed'")
    $service = $service.Replace('parse_status = "manual"', 'parse_status = "review_needed"')
    $service = $service.Replace("return 'manual'", "return 'review_needed'")
    $service = $service.Replace('return "manual"', 'return "review_needed"')

    if ($service -ne $original) {
        Copy-Item $servicePath "$servicePath.8f-backup" -Force
        Set-Content $servicePath $service -Encoding UTF8
        Write-Host 'Receipt service tweestatus-normalisatie toegepast.' -ForegroundColor Green
    } else {
        Write-Host 'Geen receipt_service statusmapping gevonden om aan te passen.' -ForegroundColor Yellow
    }
}

# 3. Frontend: eventuele Handmatig-labels/mapping naar Controle nodig normaliseren.
$frontendRoot = Join-Path $root 'frontend/src'
if (Test-Path $frontendRoot) {
    $frontendFiles = Get-ChildItem -Path $frontendRoot -Include *.js,*.jsx,*.ts,*.tsx -Recurse
    $frontendChanged = 0
    foreach ($file in $frontendFiles) {
        $text = Get-Content $file.FullName -Raw -Encoding UTF8
        $original = $text
        $text = $text.Replace('Handmatig', 'Controle nodig')
        $text = $text.Replace("manual: 'Controle nodig'", "manual: 'Controle nodig'")
        $text = $text.Replace('manual: "Controle nodig"', 'manual: "Controle nodig"')
        if ($text -ne $original) {
            Set-Content $file.FullName $text -Encoding UTF8
            $frontendChanged += 1
        }
    }
    Write-Host "Frontend-bestanden aangepast: $frontendChanged" -ForegroundColor Green
}

Write-Host ''
Write-Host '8F tweestatus-categorisering toegepast.' -ForegroundColor Green
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna Kassa en GET /api/receipt-kpi/baseline controleren.' -ForegroundColor Yellow
