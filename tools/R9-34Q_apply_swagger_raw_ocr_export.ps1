$ErrorActionPreference = 'Stop'

function Read-Utf8File([string]$Path) {
  if (-not (Test-Path $Path)) { throw "Bestand ontbreekt: $Path" }
  return [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false))
}

function Write-Utf8File([string]$Path, [string]$Content) {
  [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Replace-OrFail([string]$Content, [string]$Needle, [string]$Replacement, [string]$Label) {
  if (-not $Content.Contains($Needle)) { throw "Verwachte tekst niet gevonden voor: $Label" }
  return $Content.Replace($Needle, $Replacement)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$routePath = Join-Path $repoRoot 'backend\app\testing_receipt_line_diagnosis_routes.py'
$text = Read-Utf8File $routePath

$importNeedle = @'
    _normalize_text_lines,
'@
$importReplacement = @'
    _normalize_text_lines,
    parse_receipt_content,
'@
if (-not $text.Contains('parse_receipt_content,')) {
  $text = Replace-OrFail $text $importNeedle $importReplacement 'import parse_receipt_content'
}

$functionInsertAnchor = @'
def build_receipt_source_text_report(engine, household_id: str = '1') -> dict[str, Any]:
'@
$rawOcrFunctions = @'
def _raw_ocr_line_payload(lines: list[str] | None, confidence: float | None = None) -> dict[str, Any]:
    return {
        'available': bool(lines),
        'confidence': confidence,
        'line_count': len(lines or []),
        'lines': list(lines or []),
    }


def _normalize_text_for_raw_ocr_export(value: str | None) -> list[str]:
    try:
        return _normalize_text_lines(value or '')
    except Exception:
        return [line for line in str(value or '').splitlines() if line.strip()]


def _extract_raw_ocr_for_receipt(row: dict[str, Any]) -> dict[str, Any]:
    start = _now_ms()
    filename = str(row.get('original_filename') or 'receipt')
    mime_type = str(row.get('mime_type') or '')
    storage_path = Path(str(row.get('storage_path') or ''))
    suffix = storage_path.suffix.lower() or Path(filename).suffix.lower()
    payload: dict[str, Any] = {
        'filename': filename,
        'receipt_table_id': row.get('receipt_table_id'),
        'raw_receipt_id': row.get('raw_receipt_id'),
        'mime_type': mime_type,
        'storage_path': str(storage_path),
        'storage_exists': storage_path.exists(),
        'store_name_db': row.get('store_name'),
        'total_amount_db': _to_number(row.get('total_amount')),
        'line_count_db': _to_number(row.get('line_count')),
        'raw_ocr_scope': {
            'parser_executed': False,
            'article_detection_executed': False,
            'total_extraction_executed': False,
            'status_classification_executed': False,
            'database_changed': False,
        },
    }
    if not storage_path.exists():
        return {**payload, 'error': 'storage_file_missing', 'duration_ms': _elapsed_ms(start)}

    file_bytes = storage_path.read_bytes()
    try:
        if suffix == '.webp':
            file_bytes = _convert_webp_to_png_bytes(file_bytes)
            filename = f'{Path(filename).stem}.png'
            mime_type = 'image/png'
            suffix = '.png'

        if mime_type.startswith('image/') or suffix in {'.png', '.jpg', '.jpeg', '.webp'}:
            payload['source_kind'] = 'image'

            try:
                lines, confidence = _ocr_image_text_with_paddle(file_bytes, filename)
                payload['original_image_paddle_raw_lines'] = _raw_ocr_line_payload(lines, confidence)
            except Exception as exc:
                payload['original_image_paddle_raw_lines'] = {'error': f'{exc.__class__.__name__}: {exc}'}

            try:
                lines, confidence = _ocr_image_text_with_tesseract(file_bytes, filename)
                payload['original_image_tesseract_raw_lines'] = _raw_ocr_line_payload(lines, confidence)
            except Exception as exc:
                payload['original_image_tesseract_raw_lines'] = {'error': f'{exc.__class__.__name__}: {exc}'}

            try:
                processed_bytes, decision = apply_receipt_image_preprocessing(file_bytes, filename)
                payload['parser_input_preprocessing'] = {
                    'executed': True,
                    'selected_route': getattr(decision, 'selected_route', None),
                    'applied_steps': getattr(decision, 'applied_steps', None),
                    'fallback_reason': getattr(decision, 'fallback_reason', None),
                    'diagnostics': getattr(decision, 'diagnostics', None),
                    'bytes_changed': processed_bytes != file_bytes,
                }
                processed_filename = f'{Path(filename).stem}-parser-input.png'
                try:
                    lines, confidence = _ocr_image_text_with_paddle(processed_bytes, processed_filename)
                    payload['parser_input_paddle_raw_lines'] = _raw_ocr_line_payload(lines, confidence)
                except Exception as exc:
                    payload['parser_input_paddle_raw_lines'] = {'error': f'{exc.__class__.__name__}: {exc}'}
                try:
                    lines, confidence = _ocr_image_text_with_tesseract(processed_bytes, processed_filename)
                    payload['parser_input_tesseract_raw_lines'] = _raw_ocr_line_payload(lines, confidence)
                except Exception as exc:
                    payload['parser_input_tesseract_raw_lines'] = {'error': f'{exc.__class__.__name__}: {exc}'}
            except Exception as exc:
                payload['parser_input_preprocessing'] = {'executed': True, 'error': f'{exc.__class__.__name__}: {exc}'}

            payload['duration_ms'] = _elapsed_ms(start)
            return payload

        if mime_type == 'application/pdf' or suffix == '.pdf':
            payload['source_kind'] = 'pdf'
            try:
                direct_text = _extract_pdf_text(file_bytes)
                payload['pdf_direct_text_raw_lines'] = _raw_ocr_line_payload(_normalize_text_for_raw_ocr_export(direct_text), None)
            except Exception as exc:
                payload['pdf_direct_text_raw_lines'] = {'error': f'{exc.__class__.__name__}: {exc}'}
            try:
                ocr_text = _ocr_pdf_text_with_ocrmypdf(file_bytes, filename)
                payload['pdf_ocrmypdf_raw_lines'] = _raw_ocr_line_payload(_normalize_text_for_raw_ocr_export(ocr_text), None)
            except Exception as exc:
                payload['pdf_ocrmypdf_raw_lines'] = {'error': f'{exc.__class__.__name__}: {exc}'}
            payload['duration_ms'] = _elapsed_ms(start)
            return payload

        if mime_type == 'message/rfc822' or suffix == '.eml':
            payload['source_kind'] = 'email'
            plain_text, html_text = _extract_text_from_eml(file_bytes)
            payload['email_plain_raw_lines'] = _raw_ocr_line_payload(_normalize_text_for_raw_ocr_export(plain_text), None)
            payload['email_html_raw_lines'] = _raw_ocr_line_payload(_normalize_text_for_raw_ocr_export(html_text), None)
            payload['duration_ms'] = _elapsed_ms(start)
            return payload

        if mime_type in {'text/html', 'text/plain'} or suffix in {'.html', '.htm', '.txt'}:
            payload['source_kind'] = 'text_or_html'
            raw_text = file_bytes.decode('utf-8', errors='ignore')
            direct_text = _html_to_text(raw_text) if (mime_type == 'text/html' or suffix in {'.html', '.htm'}) else raw_text
            payload['direct_text_raw_lines'] = _raw_ocr_line_payload(_normalize_text_for_raw_ocr_export(direct_text), None)
            payload['duration_ms'] = _elapsed_ms(start)
            return payload

        return {**payload, 'source_kind': 'unsupported', 'duration_ms': _elapsed_ms(start)}
    except Exception as exc:
        return {**payload, 'error': f'{exc.__class__.__name__}: {exc}', 'duration_ms': _elapsed_ms(start)}


def build_receipt_raw_ocr_report(engine, household_id: str = '1') -> dict[str, Any]:
    start_total = _now_ms()
    with engine.begin() as conn:
        receipt_rows = _active_receipt_rows(conn, str(household_id))
    receipts = [_extract_raw_ocr_for_receipt(row) for row in receipt_rows]
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Pure raw OCR/text export before parser article detection, total extraction and status classification.',
        'scope': {
            'read_only': True,
            'active_receipts_only': True,
            'parser_executed': False,
            'article_detection_executed': False,
            'total_extraction_executed': False,
            'status_classification_executed': False,
            'database_changed': False,
            'includes_original_image_ocr': True,
            'includes_parser_input_after_preprocessing_ocr': True,
        },
        'summary': {
            'receipt_count': len(receipts),
            'image_count': sum(1 for item in receipts if item.get('source_kind') == 'image'),
            'pdf_count': sum(1 for item in receipts if item.get('source_kind') == 'pdf'),
            'email_count': sum(1 for item in receipts if item.get('source_kind') == 'email'),
            'unsupported_count': sum(1 for item in receipts if item.get('source_kind') == 'unsupported'),
        },
        'performance': {
            'total_duration_ms': _elapsed_ms(start_total),
            'per_receipt': [
                {
                    'filename': item.get('filename'),
                    'receipt_table_id': item.get('receipt_table_id'),
                    'source_kind': item.get('source_kind'),
                    'duration_ms': item.get('duration_ms'),
                    'error': item.get('error'),
                }
                for item in receipts
            ],
        },
        'receipts': receipts,
    }


'@
if (-not $text.Contains('def build_receipt_raw_ocr_report(')) {
  $text = Replace-OrFail $text $functionInsertAnchor ($rawOcrFunctions + $functionInsertAnchor) 'insert raw OCR report functions'
}

$pathsOld = @'
        '/api/testing/receipt-source-text/download',
    }
'@
$pathsNew = @'
        '/api/testing/receipt-source-text/download',
        '/api/testing/receipt-raw-ocr',
        '/api/testing/receipt-raw-ocr/download',
    }
'@
if (-not $text.Contains("'/api/testing/receipt-raw-ocr'")) {
  $text = Replace-OrFail $text $pathsOld $pathsNew 'register raw OCR paths for route replacement'
}

$routeAnchor = @'
    @app.get('/api/testing/receipt-source-text')
'@
$rawRoutes = @'
    @app.get('/api/testing/receipt-raw-ocr')
    def receipt_raw_ocr(householdId: str = '1'):
        return build_receipt_raw_ocr_report(engine, household_id=householdId)

    @app.get('/api/testing/receipt-raw-ocr/download')
    def receipt_raw_ocr_download(householdId: str = '1'):
        payload = build_receipt_raw_ocr_report(engine, household_id=householdId)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f'rezzerv_receipt_raw_ocr_all_active_{timestamp}.json'
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type='application/json; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'X-Rezzerv-Diagnosis-Selection': 'all_active_receipts',
                'X-Rezzerv-Diagnosis-Mode': 'raw-ocr-before-parser',
                'X-Rezzerv-Parser-Executed': 'false',
                'X-Rezzerv-Status-Classification-Executed': 'false',
            },
        )

'@
if (-not $text.Contains("def receipt_raw_ocr(")) {
  $text = Replace-OrFail $text $routeAnchor ($rawRoutes + $routeAnchor) 'insert raw OCR Swagger routes'
}

Write-Utf8File $routePath $text
python -m py_compile $routePath

Write-Host 'R9-34Q applied:'
Write-Host '- Swagger routes added: /api/testing/receipt-raw-ocr and /api/testing/receipt-raw-ocr/download'
Write-Host '- Export includes original-image OCR and parser-input-after-preprocessing OCR'
Write-Host '- Export is read-only and does not run parser/status classification'

git --no-pager diff -- backend/app/testing_receipt_line_diagnosis_routes.py

git add backend/app/testing_receipt_line_diagnosis_routes.py tools/R9-34Q_apply_swagger_raw_ocr_export.ps1
git commit -m 'R9-34Q add Swagger raw OCR export'
git push

Write-Host 'R9-34Q toegepast en gepusht.'
