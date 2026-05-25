param([switch]$NoCommit)
$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-30C apply failed: verwachte branch feature/r9-30a-restore-generic-rembg, maar huidige branch is '$branch'"
  exit 1
}

$python = @'
from pathlib import Path

files = {
    "screen": Path("frontend/src/ui/ScreenCard.jsx"),
    "kassa": Path("frontend/src/features/receipts/KassaPage.jsx"),
    "service": Path("backend/app/services/receipt_service.py"),
    "pre": Path("backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py"),
    "system": Path("backend/app/api/system_routes.py"),
}
for key, path in files.items():
    if not path.exists():
        raise SystemExit(f"R9-30C apply failed: bestand ontbreekt: {path}")

screen = files["screen"].read_text(encoding="utf-8-sig")
kassa = files["kassa"].read_text(encoding="utf-8-sig")
service = files["service"].read_text(encoding="utf-8-sig")
pre = files["pre"].read_text(encoding="utf-8-sig")
system = files["system"].read_text(encoding="utf-8-sig")

# ScreenCard: optionele style-prop.
if "styleOverride" not in screen:
    screen = screen.replace(
        "export default function ScreenCard({children, fullWidth=false}){",
        "export default function ScreenCard({children, fullWidth=false, style: styleOverride={}}){",
    )
    screen = screen.replace(
        '    overflow: "hidden"\n  };',
        '    overflow: "hidden"\n  };\n  const mergedStyle = {...style, ...styleOverride};',
    )
    screen = screen.replace(
        '<div style={style} data-testid="screen-card">',
        '<div style={mergedStyle} data-testid="screen-card">',
    )

# Kassa detail-layout: vaste gelijke paneelhoogte.
if "RECEIPT_DETAIL_PANEL_HEIGHT" not in kassa:
    kassa = kassa.replace(
        "const RECEIPT_INBOX_AUTO_REFRESH_MS = 60000",
        "const RECEIPT_INBOX_AUTO_REFRESH_MS = 60000\nconst RECEIPT_DETAIL_PANEL_HEIGHT = 560",
    )
kassa = kassa.replace(
    "    <ScreenCard>\n      {isCollapsed ? (",
    "    <ScreenCard style={{ height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>\n      {isCollapsed ? (",
    1,
)
kassa = kassa.replace(
    "              height: '72vh',\n              maxHeight: '72vh',",
    "              height: `${RECEIPT_DETAIL_PANEL_HEIGHT - 126}px`,\n              maxHeight: `${RECEIPT_DETAIL_PANEL_HEIGHT - 126}px`,",
)
kassa = kassa.replace(
    "    <ScreenCard>\n      <div data-testid=\"receipt-detail-page\" style={{ display: 'grid', gap: '16px' }}>",
    "    <ScreenCard style={{ height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>\n      <div data-testid=\"receipt-detail-page\" style={{ display: 'grid', gap: '16px', height: '100%', minHeight: 0, overflow: 'hidden' }}>",
    1,
)
kassa = kassa.replace("        alignItems: 'start',", "        alignItems: 'stretch',")
kassa = kassa.replace(
    "      <div style={{ minWidth: 0, width: '100%', overflow: 'visible' }}>\n        <ReceiptPreviewCard",
    "      <div style={{ minWidth: 0, width: '100%', overflow: 'visible', height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>\n        <ReceiptPreviewCard",
    1,
)
kassa = kassa.replace(
    "      <div style={{ minWidth: 0, width: '100%', overflow: 'visible' }}>\n        {receipt ? (",
    "      <div style={{ minWidth: 0, width: '100%', overflow: 'visible', height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>\n        {receipt ? (",
    1,
)

# rembg warmup.
if "def warm_receipt_image_preprocessing" not in pre:
    pre += r'''


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
'''

# OCR warmup.
if "def warm_receipt_ocr_runtime" not in service:
    service = service.replace(
        "def _ocr_image_text_with_tesseract(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:",
        r'''def warm_receipt_ocr_runtime() -> dict[str, Any]:
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


def _ocr_image_text_with_tesseract(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:''',
    )

old = '''        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
        chosen_lines = paddle_lines if image_result is paddle_result else tesseract_lines
'''
new = '''        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
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
'''
if "original_paddle_lines" not in service:
    if old not in service:
        raise SystemExit("R9-30C apply failed: OCR-keuzeblok niet gevonden")
    service = service.replace(old, new, 1)

# startup warmup in system_routes.
if "warm_receipt_runtime_at_startup" not in system:
    if "import logging" not in system:
        system = system.replace("from pathlib import Path\n", "from pathlib import Path\nimport logging\n")
    if "logger = logging.getLogger('rezzerv.api')" not in system:
        system = system.replace("router = APIRouter()\n", "router = APIRouter()\nlogger = logging.getLogger('rezzerv.api')\n")
    system += r'''


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
'''

files["screen"].write_text(screen, encoding="utf-8")
files["kassa"].write_text(kassa, encoding="utf-8")
files["service"].write_text(service, encoding="utf-8")
files["pre"].write_text(pre, encoding="utf-8")
files["system"].write_text(system, encoding="utf-8")
print("R9-30C v2 patch toegepast.")
'@

$python | python -

git diff -- frontend/src/ui/ScreenCard.jsx frontend/src/features/receipts/KassaPage.jsx backend/app/services/receipt_service.py backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py backend/app/api/system_routes.py

if (-not $NoCommit) {
  git add frontend/src/ui/ScreenCard.jsx frontend/src/features/receipts/KassaPage.jsx backend/app/services/receipt_service.py backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py backend/app/api/system_routes.py
  git commit -m 'R9-30C stabilize receipt runtime layout and store detection'
  git push
  Write-Host 'R9-30C commit gepusht.'
} else {
  Write-Host 'NoCommit gebruikt; commit/push overgeslagen.'
}
