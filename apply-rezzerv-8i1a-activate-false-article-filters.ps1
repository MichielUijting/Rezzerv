$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8I-1A false-article filters herstellen...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/services/receipt_service.py'
if (-not (Test-Path $path)) { throw "Bestand niet gevonden: $path" }

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

if ($content -notmatch 'def _looks_like_false_article_metadata_line') {
$helper = @'


def _looks_like_false_article_metadata_line(value: str | None) -> bool:
    candidate = re.sub(r'\s+', ' ', str(value or '')).strip(' .:-')
    if not candidate:
        return True
    lowered = candidate.lower()
    weekday_short = {'ma', 'di', 'wo', 'do', 'vr', 'za', 'zo', 'zon'}
    parts = lowered.split()
    if len(parts) == 2 and parts[0] in weekday_short and re.fullmatch(r'\d{1,2}[\.,:]\d{2}', parts[1]):
        return True
    if lowered.startswith('b ') and '%' in lowered and len(re.findall(r'\d+[\.,]\d{2}', lowered)) >= 3:
        return True
    if any(day in lowered for day in ('maandag', 'dinsdag', 'woensdag', 'woernsdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag')) and ('t/m' in lowered or ' tot ' in lowered):
        return True
    if re.fullmatch(r'\d{1,6}[\.,]\d{2}', candidate):
        return True
    if any(token in lowered for token in ('zegel', 'zegels', 'zege1s', 'pluspunten')) and (':' in lowered or sum(ch.isdigit() for ch in candidate) >= 4):
        return True
    if not re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]', candidate) and len(re.findall(r'\d+[\.,]\d{2}', candidate)) >= 2:
        return True
    return False
'@
    $anchor = 'def _should_skip_receipt_line(line: str, *, store_name: str | None = None, filename: str | None = None) -> bool:'
    if (-not $content.Contains($anchor)) { throw 'Anchor _should_skip_receipt_line niet gevonden.' }
    $content = $content.Replace($anchor, $helper + "`r`n`r`n" + $anchor)
}

$old = "def _should_skip_receipt_line(line: str, *, store_name: str | None = None, filename: str | None = None) -> bool:`r`n    lowered = str(line or '').strip().lower()"
$new = "def _should_skip_receipt_line(line: str, *, store_name: str | None = None, filename: str | None = None) -> bool:`r`n    if _looks_like_false_article_metadata_line(line):`r`n        return True`r`n    lowered = str(line or '').strip().lower()"
if ($content.Contains($old)) { $content = $content.Replace($old, $new) }

$old2 = "    lowered = candidate.lower()`r`n    if re.fullmatch(r'[-+]?\d+(?:[\.,]\d+)?(?:\s+[-+]?\d+(?:[\.,]\d+)?)*', candidate):"
$new2 = "    lowered = candidate.lower()`r`n    if _looks_like_false_article_metadata_line(candidate):`r`n        return True`r`n    if re.fullmatch(r'[-+]?\d+(?:[\.,]\d+)?(?:\s+[-+]?\d+(?:[\.,]\d+)?)*', candidate):"
if ($content.Contains($old2)) { $content = $content.Replace($old2, $new2) }

$old3 = "        label_value = _clean_receipt_label(label)`r`n        if not label_value or len(label_value) < 2 or label_value.replace(' ', '').isdigit():"
$new3 = "        label_value = _clean_receipt_label(label)`r`n        if _looks_like_false_article_metadata_line(label_value):`r`n            return None`r`n        if not label_value or len(label_value) < 2 or label_value.replace(' ', '').isdigit():"
if ($content.Contains($old3)) { $content = $content.Replace($old3, $new3) }

$content = $content.Replace("'zegel', 'zegels', 'koopzegel',", "'zegel', 'zegels', 'zege1s', 'koopzegel',")

if ($content -ne $original) {
    Copy-Item $path "$path.8i1a-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host '8I-1A filters actief gemaakt.' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast; controleer of filters al actief zijn.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
