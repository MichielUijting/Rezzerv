$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8E store-specific article amount rules starten...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/services/receipt_service.py'
if (-not (Test-Path $path)) {
    throw "Bestand niet gevonden: $path"
}

$content = Get-Content $path -Raw

if ($content -notmatch 'def _store_specific_article_amount_adjustments') {
$insert = @'


def _store_specific_article_amount_adjustments(
    lines: list[dict[str, Any]],
    text_lines: list[str],
    *,
    store_name: str | None = None,
    filename: str | None = None,
    total_amount: Decimal | None = None,
) -> list[dict[str, Any]]:
    """Conservative retailer-specific article amount adjustments.

    This does not determine status. It only improves article-line financials
    before the existing total validation decides whether the receipt is safe.
    """
    adjusted = list(lines or [])
    context = f"{store_name or ''} {filename or ''}".lower()

    if 'albert heijn' in context or re.search(r'\bah\b', context):
        adjusted = _ensure_ah_savings_lines(adjusted, text_lines)

    if 'jumbo' in context:
        adjusted = _ensure_jumbo_savings_lines(adjusted, text_lines)
        adjusted = _repair_jumbo_quantity_lines(adjusted, text_lines)

    if 'aldi' in context:
        adjusted = _reject_unsafe_aldi_negative_lines(adjusted)

    if 'plus' in context:
        adjusted = _reject_impossible_large_lines(adjusted, total_amount)

    return adjusted


def _line_identity_key(line: dict[str, Any]) -> tuple[str, str]:
    label = re.sub(r'\s+', ' ', str(line.get('raw_label') or line.get('normalized_label') or '')).strip().lower()
    amount = str(line.get('line_total') or '')
    return label, amount


def _append_if_missing(lines: list[dict[str, Any]], next_line: dict[str, Any]) -> None:
    keys = {_line_identity_key(line) for line in lines}
    if _line_identity_key(next_line) not in keys:
        lines.append(next_line)


def _ensure_ah_savings_lines(lines: list[dict[str, Any]], text_lines: list[str]) -> list[dict[str, Any]]:
    result = list(lines or [])
    pattern = re.compile(r'(?i)^(?:(?P<qty>\d+)\s+)?(?P<label>koopzegels?(?:\s+premium)?)\s+(?P<amount>\d{1,4}[\.,]\d{2})$')
    for source_index, raw_line in enumerate(text_lines or []):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        match = pattern.match(normalized)
        if not match:
            continue
        amount = _parse_decimal(match.group('amount'))
        if amount is None or amount <= 0:
            continue
        quantity = _parse_quantity(match.group('qty')) if match.group('qty') else Decimal('1')
        label = _clean_receipt_label(match.group('label'))
        unit_price = (amount / quantity).quantize(Decimal('0.01')) if quantity and quantity > 0 else amount
        _append_if_missing(result, {
            'raw_label': label,
            'normalized_label': label,
            'quantity': _amount_to_float(quantity),
            'unit': None,
            'unit_price': _amount_to_float(unit_price),
            'line_total': _amount_to_float(amount),
            'discount_amount': None,
            'barcode': None,
            'confidence_score': 0.86,
            'source_index': source_index,
        })
    return result


def _ensure_jumbo_savings_lines(lines: list[dict[str, Any]], text_lines: list[str]) -> list[dict[str, Any]]:
    result = list(lines or [])
    pattern = re.compile(r'(?i)^(?:(?P<qty>\d+)\s*)?(?P<label>koopzegel\s+digitaal|koopzegels?)(?:\s+premium)?\s+(?P<amount>\d{1,4}[\.,]\d{2})$')
    for source_index, raw_line in enumerate(text_lines or []):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        match = pattern.match(normalized)
        if not match:
            continue
        amount = _parse_decimal(match.group('amount'))
        if amount is None or amount <= 0:
            continue
        quantity = _parse_quantity(match.group('qty')) if match.group('qty') else Decimal('1')
        label = _clean_receipt_label(match.group('label'))
        unit_price = (amount / quantity).quantize(Decimal('0.01')) if quantity and quantity > 0 else amount
        _append_if_missing(result, {
            'raw_label': label,
            'normalized_label': label,
            'quantity': _amount_to_float(quantity),
            'unit': None,
            'unit_price': _amount_to_float(unit_price),
            'line_total': _amount_to_float(amount),
            'discount_amount': None,
            'barcode': None,
            'confidence_score': 0.86,
            'source_index': source_index,
        })
    return result


def _repair_jumbo_quantity_lines(lines: list[dict[str, Any]], text_lines: list[str]) -> list[dict[str, Any]]:
    result = list(lines or [])
    pattern = re.compile(r'(?i)^(?P<label>.+?)\s+(?P<qty>\d+)\s*[xX]\s+(?P<unit>\d{1,4}[\.,]\d{2})\s+(?P<total>\d{1,4}[\.,]\d{2})$')
    for source_index, raw_line in enumerate(text_lines or []):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        lowered = normalized.lower()
        if any(token in lowered for token in ('totaal', 'subtotaal', 'betaling', 'bankpas', 'btw')):
            continue
        match = pattern.match(normalized)
        if not match:
            continue
        label = _clean_receipt_label(match.group('label'))
        if not label or _looks_like_non_product_receipt_label(label):
            continue
        quantity = _parse_quantity(match.group('qty'))
        unit_price = _parse_decimal(match.group('unit'))
        line_total = _parse_decimal(match.group('total'))
        if quantity is None or unit_price is None or line_total is None:
            continue
        if quantity <= 0 or line_total <= 0:
            continue
        _append_if_missing(result, {
            'raw_label': label,
            'normalized_label': label,
            'quantity': _amount_to_float(quantity),
            'unit': None,
            'unit_price': _amount_to_float(unit_price),
            'line_total': _amount_to_float(line_total),
            'discount_amount': None,
            'barcode': None,
            'confidence_score': 0.84,
            'source_index': source_index,
        })
    return result


def _reject_unsafe_aldi_negative_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    allowed_negative_tokens = ('korting', 'retour', 'statiegeld retour', 'terug')
    for line in lines or []:
        amount = _parse_decimal(str(line.get('line_total')))
        label = str(line.get('raw_label') or line.get('normalized_label') or '').lower()
        if amount is not None and amount < 0 and not any(token in label for token in allowed_negative_tokens):
            continue
        result.append(line)
    return result


def _reject_impossible_large_lines(lines: list[dict[str, Any]], total_amount: Decimal | None) -> list[dict[str, Any]]:
    if total_amount is None or total_amount <= 0:
        return list(lines or [])
    limit = (Decimal(total_amount).quantize(Decimal('0.01')) * Decimal('1.50')).quantize(Decimal('0.01'))
    result: list[dict[str, Any]] = []
    for line in lines or []:
        amount = _parse_decimal(str(line.get('line_total')))
        if amount is not None and amount > limit:
            continue
        result.append(line)
    return result
'@

    $anchor = "def _failed_receipt_result(confidence: float = 0.0) -> ReceiptParseResult:"
    $content = $content.Replace($anchor, $insert + "`r`n`r`n" + $anchor)
}

if ($content -notmatch '_store_specific_article_amount_adjustments\(' -or $content -notmatch 'lines = _store_specific_article_amount_adjustments\(') {
    $old = "    lines = _filter_non_product_receipt_lines(lines)`n    discount_total = _apply_discount_entries(lines, _extract_discount_entries(text_lines))"
    $new = "    lines = _store_specific_article_amount_adjustments(lines, text_lines, store_name=store_name, filename=filename, total_amount=total_amount)`n    lines = _filter_non_product_receipt_lines(lines)`n    discount_total = _apply_discount_entries(lines, _extract_discount_entries(text_lines))"
    $content = $content.Replace($old, $new)
}

# Fix over-aggressive generic non-product filtering for savings lines: keep explicit savings/points lines.
$content = $content -replace "'zegel', 'zegels', 'koopzegel', 'koopzegels', 'pluspunten', 'spaarkaart',", "'spaarkaart',"

Set-Content $path $content -Encoding UTF8

Write-Host ''
Write-Host '8E winkel-specifieke artikelbedragregels toegepast.' -ForegroundColor Green
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host ''
Write-Host 'Daarna moeten bestaande bonnen opnieuw geparsed worden om de KPI te verbeteren.' -ForegroundColor Yellow
