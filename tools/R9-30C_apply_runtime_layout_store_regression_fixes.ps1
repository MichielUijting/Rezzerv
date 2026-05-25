param(
  [switch]$NoCommit
)

$ErrorActionPreference = 'Stop'

function Fail($message) {
  Write-Error "R9-30C apply failed: $message"
  exit 1
}

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Fail "verwachte branch feature/r9-30a-restore-generic-rembg, maar huidige branch is '$branch'"
}

$screenCardPath = 'frontend/src/ui/ScreenCard.jsx'
$kassaPath = 'frontend/src/features/receipts/KassaPage.jsx'
$receiptServicePath = 'backend/app/services/receipt_service.py'
$preprocessingPath = 'backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py'
$systemRoutesPath = 'backend/app/api/system_routes.py'

foreach ($path in @($screenCardPath, $kassaPath, $receiptServicePath, $preprocessingPath, $systemRoutesPath)) {
  if (-not (Test-Path $path)) { Fail "bestand ontbreekt: $path" }
}

$screenCard = Get-Content $screenCardPath -Raw
$kassa = Get-Content $kassaPath -Raw
$receiptService = Get-Content $receiptServicePath -Raw
$preprocessing = Get-Content $preprocessingPath -Raw
$systemRoutes = Get-Content $systemRoutesPath -Raw

# 1. ScreenCard krijgt optionele style-prop voor vaste detailpanelen zonder globale regressie.
if ($screenCard -notmatch 'function ScreenCard\(\{children, fullWidth=false, style: styleOverride=\{\}\}\)') {
  $screenCard = $screenCard.Replace(
    'export default function ScreenCard({children, fullWidth=false}){',
    'export default function ScreenCard({children, fullWidth=false, style: styleOverride={}}){'
  )
  $screenCard = $screenCard.Replace(
    '    overflow: "hidden"' + "`n" + '  };',
    '    overflow: "hidden"' + "`n" + '  };' + "`n" + '  const mergedStyle = {...style, ...styleOverride};'
  )
  $screenCard = $screenCard.Replace(
    '<div style={style} data-testid="screen-card">',
    '<div style={mergedStyle} data-testid="screen-card">'
  )
}

# 2. Kassa detail-layout: vaste gelijke paneelhoogte voor preview en bonregels, max 10 regels.
if ($kassa -notmatch 'RECEIPT_DETAIL_PANEL_HEIGHT') {
  $kassa = $kassa.Replace(
    'const RECEIPT_INBOX_AUTO_REFRESH_MS = 60000',
    'const RECEIPT_INBOX_AUTO_REFRESH_MS = 60000' + "`n" + 'const RECEIPT_DETAIL_PANEL_HEIGHT = 560'
  )
}

$kassa = $kassa.Replace(
  "    <ScreenCard>`n      {isCollapsed ? (",
  "    <ScreenCard style={{ height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>`n      {isCollapsed ? ("
)

$kassa = $kassa.Replace(
  "              height: '72vh',`n              maxHeight: '72vh',",
  "              height: `${RECEIPT_DETAIL_PANEL_HEIGHT - 126}px`, `n              maxHeight: `${RECEIPT_DETAIL_PANEL_HEIGHT - 126}px`,"
)

$kassa = $kassa.Replace(
  "    <ScreenCard>`n      <div data-testid=\"receipt-detail-page\" style={{ display: 'grid', gap: '16px' }}>",
  "    <ScreenCard style={{ height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>`n      <div data-testid=\"receipt-detail-page\" style={{ display: 'grid', gap: '16px', height: '100%', minHeight: 0, overflow: 'hidden' }}>"
)

$kassa = $kassa.Replace(
  "        alignItems: 'start',",
  "        alignItems: 'stretch',"
)

$kassa = $kassa.Replace(
  "      <div style={{ minWidth: 0, width: '100%', overflow: 'visible' }}>",
  "      <div style={{ minWidth: 0, width: '100%', overflow: 'visible', height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>"
)

# Replace both child wrappers only once each; avoid changing unrelated wrappers repeatedly on rerun.
$kassa = $kassa.Replace(
  "      <div style={{ minWidth: 0, width: '100%', overflow: 'visible', height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>`n        {receipt ? (",
  "      <div style={{ minWidth: 0, width: '100%', overflow: 'visible', height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>`n        {receipt ? ("
)

# 3. Preprocessing: publieke warmupfunctie voor rembg, zonder status/parsermutatie.
if ($preprocessing -notmatch 'def warm_receipt_image_preprocessing') {
  $preprocessing += @'


def warm_receipt_image_preprocessing() -> dict[str, Any]:
    """Warm the rembg runtime so the first user upload does not pay model initialization."""
    diagnostics: dict[str, Any] = {"warmup": "receipt_image_preprocessing"}
    if rembg_remove is None:
        diagnostics["status"] = "rembg_unavailable"
        return diagnostics
    try:
        sample = Image.new("RGB", (96, 160), (245, 245, 245))
        buffer = BytesIO()
        sample.save(buffer, format="PNG")
        _ = rembg_remove(buffer.getvalue())
        diagnostics["status"] = "ok"
    except Exception as exc:
        diagnostics["status"] = "failed"
        diagnostics["error"] = f"{type(exc).__name__}: {exc}"
    return diagnostics
'@
}

# 4. Receipt service: OCR op origineel en bewerkt vergelijken, zodat rembg store-detectie niet kan degraderen.
if ($receiptService -notmatch 'def warm_receipt_ocr_runtime') {
  $receiptService = $receiptService.Replace(
    "def _ocr_image_text_with_tesseract(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:",
    @'
def warm_receipt_ocr_runtime() -> dict[str, Any]:
    """Warm OCR dependencies before the first user upload."""
    result: dict[str, Any] = {"warmup": "receipt_ocr_runtime"}
    try:
        if Image is None:
            result["paddle"] = "pillow_unavailable"
            return result
        sample = Image.new("RGB", (320, 220), "white")
        buffer = io.BytesIO()
        sample.save(buffer, format="PNG")
        paddle_lines, _ = _ocr_image_text_with_paddle(buffer.getvalue(), "warmup.png")
        result["paddle"] = "ok" if paddle_lines is not None else "no_lines"
    except Exception as exc:
        result["paddle"] = f"failed:{type(exc).__name__}"
    return result


def _ocr_image_text_with_tesseract(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:
'@
  )
}

$oldImageBlock = @'
        paddle_lines, paddle_confidence = _ocr_image_text_with_paddle(ocr_file_bytes, ocr_filename)
        tesseract_lines, tesseract_confidence = _ocr_image_text_with_tesseract(ocr_file_bytes, ocr_filename)

        paddle_result = _parse_result_from_text_lines(
            paddle_lines,
            filename,
            rich_confidence=0.84,
            partial_confidence=0.64,
            review_confidence=0.36,
        ) if paddle_lines else _failed_receipt_result(0.0)
        tesseract_result = _parse_result_from_text_lines(
            tesseract_lines,
            filename,
            rich_confidence=0.82,
            partial_confidence=0.62,
            review_confidence=0.34,
        ) if tesseract_lines else _failed_receipt_result(0.0)

        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
        chosen_lines = paddle_lines if image_result is paddle_result else tesseract_lines
'@
$newImageBlock = @'
        paddle_lines, paddle_confidence = _ocr_image_text_with_paddle(ocr_file_bytes, ocr_filename)
        tesseract_lines, tesseract_confidence = _ocr_image_text_with_tesseract(ocr_file_bytes, ocr_filename)

        paddle_result = _parse_result_from_text_lines(
            paddle_lines,
            filename,
            rich_confidence=0.84,
            partial_confidence=0.64,
            review_confidence=0.36,
        ) if paddle_lines else _failed_receipt_result(0.0)
        tesseract_result = _parse_result_from_text_lines(
            tesseract_lines,
            filename,
            rich_confidence=0.82,
            partial_confidence=0.62,
            review_confidence=0.34,
        ) if tesseract_lines else _failed_receipt_result(0.0)

        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
        chosen_lines = paddle_lines if image_result is paddle_result else tesseract_lines

        if ocr_file_bytes != file_bytes:
            original_paddle_lines, original_paddle_confidence = _ocr_image_text_with_paddle(file_bytes, filename)
            original_tesseract_lines, original_tesseract_confidence = _ocr_image_text_with_tesseract(file_bytes, filename)
            original_paddle_result = _parse_result_from_text_lines(
                original_paddle_lines,
                filename,
                rich_confidence=0.82,
                partial_confidence=0.62,
                review_confidence=0.34,
            ) if original_paddle_lines else _failed_receipt_result(0.0)
            original_tesseract_result = _parse_result_from_text_lines(
                original_tesseract_lines,
                filename,
                rich_confidence=0.80,
                partial_confidence=0.60,
                review_confidence=0.32,
            ) if original_tesseract_lines else _failed_receipt_result(0.0)
            original_result = _choose_better_receipt_result(original_paddle_result, original_tesseract_result)
            best_result = _choose_better_receipt_result(image_result, original_result)
            if best_result is not image_result:
                image_result = best_result
                if best_result is original_paddle_result:
                    chosen_confidence = original_paddle_confidence
                    chosen_lines = original_paddle_lines
                else:
                    chosen_confidence = original_tesseract_confidence
                    chosen_lines = original_tesseract_lines
'@
if ($receiptService.Contains($oldImageBlock)) {
  $receiptService = $receiptService.Replace($oldImageBlock, $newImageBlock)
} else {
  Write-Host 'OCR comparison block niet gevonden of al aangepast.'
}

# 5. System startup warmup: warm rembg + OCR bij startup, met logging en zonder upload te blokkeren op onbekende fout.
if ($systemRoutes -notmatch 'warm_receipt_runtime_at_startup') {
  $systemRoutes = $systemRoutes.Replace(
    'from pathlib import Path' + "`n",
    'from pathlib import Path' + "`n" + 'import logging' + "`n"
  )
  $systemRoutes = $systemRoutes.Replace(
    'router = APIRouter()' + "`n",
    'router = APIRouter()' + "`n" + 'logger = logging.getLogger(''rezzerv.api'')' + "`n"
  )
  $systemRoutes += @'


@router.on_event('startup')
def warm_receipt_runtime_at_startup():
    """Warm receipt OCR/preprocessing runtime to avoid first-upload cold-start failures."""
    try:
        from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import warm_receipt_image_preprocessing
        from app.services.receipt_service import warm_receipt_ocr_runtime
        preprocessing_result = warm_receipt_image_preprocessing()
        ocr_result = warm_receipt_ocr_runtime()
        logger.info('Receipt runtime warmup voltooid: preprocessing=%s ocr=%s', preprocessing_result, ocr_result)
    except Exception as exc:
        logger.warning('Receipt runtime warmup mislukt; upload fallback blijft actief: %s', exc)
'@
}

Set-Content $screenCardPath $screenCard -Encoding UTF8
Set-Content $kassaPath $kassa -Encoding UTF8
Set-Content $receiptServicePath $receiptService -Encoding UTF8
Set-Content $preprocessingPath $preprocessing -Encoding UTF8
Set-Content $systemRoutesPath $systemRoutes -Encoding UTF8

Write-Host 'R9-30C patch toegepast. Diff:'
git diff -- $screenCardPath $kassaPath $receiptServicePath $preprocessingPath $systemRoutesPath

if (-not $NoCommit) {
  git add $screenCardPath $kassaPath $receiptServicePath $preprocessingPath $systemRoutesPath
  git commit -m 'R9-30C stabilize receipt runtime layout and store detection'
  git push
  Write-Host 'R9-30C commit gepusht.'
} else {
  Write-Host 'NoCommit gebruikt; commit/push overgeslagen.'
}
