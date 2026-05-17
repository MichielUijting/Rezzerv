$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host 'Rezzerv 8I-2 line-flow trace endpoint toevoegen...' -ForegroundColor Cyan

$path = Join-Path $root 'backend/app/main.py'
if (-not (Test-Path $path)) { throw "Bestand niet gevonden: $path" }

$content = Get-Content $path -Raw -Encoding UTF8
$original = $content

$imports = @(
    'from app.services.receipt_service import _extract_receipt_lines',
    'from app.services.receipt_service import _extract_sparse_receipt_lines',
    'from app.services.receipt_service import _filter_non_product_receipt_lines',
    'from app.services.receipt_service import _should_skip_receipt_line',
    'from app.services.receipt_service import _looks_like_non_product_receipt_label'
)
foreach ($line in $imports) {
    if ($content -notmatch [regex]::Escape($line)) {
        $content = $line + "`r`n" + $content
    }
}

if ($content -notmatch 'receipt-line-flow-trace') {
$endpoint = @'


@app.get("/api/testing/receipt-line-flow-trace")
def receipt_line_flow_trace():
    test_inputs = [
        {"input": "ZON 10.00", "store": "ALDI", "filename": "Aldi foto 1.jpg"},
        {"input": "ZA 8.00", "store": "ALDI", "filename": "Aldi foto 2.jpg"},
        {"input": "ZO 12.00", "store": "ALDI", "filename": "Aldi foto 2.jpg"},
        {"input": "B 9,00% 6,01 0,54", "store": "ALDI", "filename": "Aldi foto 1.jpg"},
        {"input": "B 9,00% 4,59 0,41", "store": "ALDI", "filename": "Aldi foto 2.jpg"},
        {"input": "Maandag t/m Woernsdag", "store": "Jumbo", "filename": "Jumbo foto 1.jpeg"},
        {"input": "50.89", "store": "Plus", "filename": "Plus foto 2.jpeg"},
        {"input": "99 ,64 23,92 4,92", "store": "Plus", "filename": "Plus foto 2.jpeg"},
        {"input": "26 11:01 I08335 175 zege1s +", "store": "Plus", "filename": "Plus foto 2.jpeg"},
    ]

    results = []
    for case in test_inputs:
        raw = case["input"]
        store = case["store"]
        filename = case["filename"]
        normalized = raw.strip()

        direct_filter = bool(_looks_like_false_article_metadata_line(normalized))
        should_skip = bool(_should_skip_receipt_line(normalized, store_name=store, filename=filename))
        label_filter = bool(_looks_like_non_product_receipt_label(normalized))

        normal_lines = _extract_receipt_lines([normalized], store_name=store, filename=filename)
        normal_filtered = _filter_non_product_receipt_lines(normal_lines)
        sparse_lines = _extract_sparse_receipt_lines([normalized], filename=filename, store_name=store)
        sparse_filtered = _filter_non_product_receipt_lines(sparse_lines)

        paths = []
        paths.append({
            "code_path": "direct_filter_helper",
            "filter_called": True,
            "filter_result": direct_filter,
            "append_called": False,
            "output_count": 0,
            "stored_result": False,
        })
        paths.append({
            "code_path": "_should_skip_receipt_line",
            "filter_called": True,
            "filter_result": should_skip,
            "append_called": False,
            "output_count": 0,
            "stored_result": False,
        })
        paths.append({
            "code_path": "_looks_like_non_product_receipt_label",
            "filter_called": True,
            "filter_result": label_filter,
            "append_called": False,
            "output_count": 0,
            "stored_result": False,
        })
        paths.append({
            "code_path": "_extract_receipt_lines",
            "filter_called": True,
            "filter_result": len(normal_lines) == 0,
            "append_called": len(normal_lines) > 0,
            "output_count": len(normal_lines),
            "stored_result": len(normal_lines) > 0,
            "outputs": normal_lines,
        })
        paths.append({
            "code_path": "_extract_receipt_lines_then_filter_non_product",
            "filter_called": True,
            "filter_result": len(normal_filtered) == 0,
            "append_called": len(normal_lines) > 0,
            "output_count": len(normal_filtered),
            "stored_result": len(normal_filtered) > 0,
            "outputs": normal_filtered,
        })
        paths.append({
            "code_path": "_extract_sparse_receipt_lines",
            "filter_called": True,
            "filter_result": len(sparse_lines) == 0,
            "append_called": len(sparse_lines) > 0,
            "output_count": len(sparse_lines),
            "stored_result": len(sparse_lines) > 0,
            "outputs": sparse_lines,
        })
        paths.append({
            "code_path": "_extract_sparse_receipt_lines_then_filter_non_product",
            "filter_called": True,
            "filter_result": len(sparse_filtered) == 0,
            "append_called": len(sparse_lines) > 0,
            "output_count": len(sparse_filtered),
            "stored_result": len(sparse_filtered) > 0,
            "outputs": sparse_filtered,
        })

        bypass_detected = any(path.get("stored_result") for path in paths if path.get("code_path") in ["_extract_receipt_lines", "_extract_sparse_receipt_lines"])

        results.append({
            "input_line": raw,
            "normalized_line": normalized,
            "store_name": store,
            "filename": filename,
            "expected_filtered": True,
            "direct_filter_result": direct_filter,
            "bypass_detected": bypass_detected,
            "paths": paths,
        })

    return {
        "success": True,
        "purpose": "Read-only trace van bekende false article lines door actieve parserfuncties.",
        "results": results,
    }
'@
$content += $endpoint
}

if ($content -ne $original) {
    Copy-Item $path "$path.8i2-line-flow-trace-backup" -Force
    Set-Content $path $content -Encoding UTF8
    Write-Host 'Line-flow trace endpoint toegevoegd.' -ForegroundColor Green
} else {
    Write-Host 'Geen wijziging toegepast; endpoint lijkt al aanwezig.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Volgende stap:' -ForegroundColor Yellow
Write-Host 'docker compose up -d --build'
Write-Host 'Daarna GET /api/testing/receipt-line-flow-trace uitvoeren.' -ForegroundColor Yellow
