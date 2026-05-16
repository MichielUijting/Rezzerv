$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8I-1 false article filtering starten...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/services/receipt_service.py'
if (-not (Test-Path $path)) {
    throw "Bestand niet gevonden: $path"
}

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

# 1. Versterk _should_skip_receipt_line met weekdag/openingstijd/actieperiode-regels.
$anchor = "    if any(marker in lowered for marker in skip_markers):`r`n        return True"
$insert = @'
    # 8I-1: metadata/openingstijd/actieperiode-regels mogen nooit artikelregels worden.
    weekday_tokens = ('maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag', 'ma', 'di', 'wo', 'do', 'vr', 'za', 'zo', 'zon')
    if re.match(r'^(?:ma|di|wo|do|vr|za|zo|zon)\s+\d{1,2}[\.,:]\d{2}\b', lowered):
        return True
    if any(token in lowered for token in weekday_tokens) and re.search(r'\bt/m\b|\btot\b|\d{1,2}[\.,:]\d{2}', lowered):
        return True
'@
if ($content.Contains($anchor) -and $content -notmatch '8I-1: metadata/openingstijd') {
    $content = $content.Replace($anchor, $anchor + "`r`n" + $insert)
}

# 2. Versterk _looks_like_non_product_receipt_label met concrete metadata-patronen.
$anchor2 = "    if re.fullmatch(r'[\d\s,\.:%/\-+xX]+', candidate):`r`n        return True"
$insert2 = @'
    # 8I-1: ALDI openingstijden en BTW-samenvattingen.
    if re.match(r'^(?:ma|di|wo|do|vr|za|zo|zon)\s+\d{1,2}[\.,:]\d{2}\b', lowered):
        return True
    if re.match(r'^[A-Z]\s+\d{1,2}[\.,]\d{2}%\s+\d{1,6}[\.,]\d{2}\s+\d{1,6}[\.,]\d{2}', candidate):
        return True
    if re.match(r'^[A-Z]\s+\d{1,2}[\.,]\d{2}\s+\d{1,6}[\.,]\d{2}\s+\d{1,6}[\.,]\d{2}', candidate):
        return True
    # 8I-1: losse totaalbedragen en kassacode-/zegelregels, met of zonder OCR-ruis.
    if re.fullmatch(r'\d{1,6}[\.,]\d{2}', candidate):
        return True
    if re.search(r'\b\d{1,2}:\d{2}\b', lowered) and re.search(r'\bzegels?\b|\bzege1s\b|\bpluspunten\b', lowered):
        return True
    if re.search(r'\bzegels?\b|\bzege1s\b|\bpluspunten\b', lowered) and sum(ch.isdigit() for ch in candidate) >= 4:
        return True
    # 8I-1: Jumbo/AH actieperiode en weekdagregels.
    if any(token in lowered for token in ('maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag')) and re.search(r'\bt/m\b|\btot\b', lowered):
        return True
'@
if ($content.Contains($anchor2) -and $content -notmatch '8I-1: ALDI openingstijden') {
    $content = $content.Replace($anchor2, $anchor2 + "`r`n" + $insert2)
}

# 3. Breid non-product tokenlijst uit met OCR-varianten.
$content = $content.Replace(
    "'zegel', 'zegels', 'koopzegel', 'koopzegels', 'pluspunten', 'spaarkaart',",
    "'zegel', 'zegels', 'zege1s', 'koopzegel', 'koopzegels', 'pluspunten', 'spaarkaart', 'openingstijd',"
)

if ($content -ne $original) {
    Copy-Item $path "$path.8i1-false-article-filtering-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'False article filtering toegepast in receipt_service.py' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast; filters lijken al aanwezig of code wijkt af.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna 14 bonnen opnieuw importeren en receipt-line-diagnosis/download draaien.' -ForegroundColor Yellow
