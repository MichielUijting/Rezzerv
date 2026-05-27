$ErrorActionPreference = 'Stop'

function Read-Utf8File([string]$Path) {
  if (-not (Test-Path $Path)) {
    throw "Bestand ontbreekt: $Path"
  }
  return [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($true))
}

function Write-Utf8File([string]$Path, [string]$Content) {
  [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($true))
}

function TextFromCodes([int[]]$Codes) {
  $chars = New-Object char[] ($Codes.Count)
  for ($i = 0; $i -lt $Codes.Count; $i += 1) {
    $chars[$i] = [char]$Codes[$i]
  }
  return [string]::new($chars)
}

function Replace-OrFail([string]$Content, [string]$Needle, [string]$Replacement, [string]$Label) {
  if (-not $Content.Contains($Needle)) {
    throw "Verwachte tekst niet gevonden voor: $Label"
  }
  return $Content.Replace($Needle, $Replacement)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$kassaPath = Join-Path $repoRoot 'frontend\src\features\receipts\KassaPage.jsx'
$previewRoutesPath = Join-Path $repoRoot 'backend\app\api\receipt_preview_routes.py'
$normalizerPath = Join-Path $repoRoot 'backend\app\domains\receipts\image\receipt_photo_normalizer.py'

# 1. Frontend mojibake: ASCII-safe repair.
# No literal mojibake characters are used here, because those broke PowerShell parsing on Windows.
$kassa = Read-Utf8File $kassaPath
$kassaOriginal = $kassa

$ellipsisActual = TextFromCodes @(0x00E2, 0x20AC, 0x00A6)
$ellipsisDouble = TextFromCodes @(0x00C3, 0x00A2, 0x00E2, 0x201A, 0x00AC, 0x00C2, 0x00A6)
$minusActual = TextFromCodes @(0x00E2, 0x02C6, 0x2019)
$minusDouble = TextFromCodes @(0x00C3, 0x00A2, 0x00CB, 0x2020, 0x00E2, 0x20AC, 0x2122)

$kassa = $kassa.Replace($ellipsisActual, '...')
$kassa = $kassa.Replace($ellipsisDouble, '...')
$kassa = $kassa.Replace($minusActual, '-')
$kassa = $kassa.Replace($minusDouble, '-')

if ($kassa -ne $kassaOriginal) {
  Write-Utf8File $kassaPath $kassa
}

# 2. Kassa processed preview: show the visual normalized receipt first, not the OCR-threshold image.
# OCR-ready remains a fallback only. This restores the preview to the receipt image that the user can inspect.
$preview = Read-Utf8File $previewRoutesPath
$oldPreviewBlock = @'
        processed_path = None
        if normalized.success and normalized.ocr_ready_path and Path(normalized.ocr_ready_path).exists():
            processed_path = Path(normalized.ocr_ready_path)
        if processed_path is None:
            processed_path = _generate_fallback_processed_preview(storage_path)
'@
$newPreviewBlock = @'
        processed_path = None
        if normalized.success and normalized.normalized_path and Path(normalized.normalized_path).exists():
            processed_path = Path(normalized.normalized_path)
        elif normalized.success and normalized.ocr_ready_path and Path(normalized.ocr_ready_path).exists():
            processed_path = Path(normalized.ocr_ready_path)
        if processed_path is None:
            processed_path = _generate_fallback_processed_preview(storage_path)
'@
$preview = Replace-OrFail $preview $oldPreviewBlock $newPreviewBlock 'processed preview must prefer normalized_path'
Write-Utf8File $previewRoutesPath $preview

# 3. Photo normalizer: never accept a near-full-frame paper mask as the receipt region.
# AH foto 3 showed exactly this failure: the background/floor became the selected region.
$normalizer = Read-Utf8File $normalizerPath
$oldNormalizerBlock = @'
        # Keep near-full-frame good receipts intact, but reject a full-frame background masquerading as a receipt.
        if best_area_ratio > MAX_RECEIPT_AREA_RATIO_FOR_BACKGROUND and best_continuity < 0.82:
            diagnostics['region_isolation_reason'] = 'mask_too_large_without_continuity'
            return None, best_score, 'region_isolation_mask_too_large', diagnostics
'@
$newNormalizerBlock = @'
        # Reject near-full-frame masks. In oblique receipt photos this means the background/table/floor
        # has been selected instead of the receipt. Do not let that background drive rotation/cropping.
        if best_area_ratio > MAX_RECEIPT_AREA_RATIO_FOR_BACKGROUND:
            diagnostics['region_isolation_reason'] = 'mask_too_large_background_candidate'
            return None, best_score, 'region_isolation_mask_too_large_background_candidate', diagnostics
'@
$normalizer = Replace-OrFail $normalizer $oldNormalizerBlock $newNormalizerBlock 'reject full-frame background mask'
Write-Utf8File $normalizerPath $normalizer

# Lightweight validation: no known mojibake remains in KassaPage and Python files still compile.
$kassaCheck = Read-Utf8File $kassaPath
if ($kassaCheck.Contains($ellipsisActual) -or $kassaCheck.Contains($ellipsisDouble) -or $kassaCheck.Contains($minusActual) -or $kassaCheck.Contains($minusDouble)) {
  throw 'Mojibake-resten gevonden in KassaPage.jsx'
}

python -m py_compile $previewRoutesPath $normalizerPath

Write-Host 'R9-34G-FIX applied:'
Write-Host '- KassaPage mojibake labels replaced with ASCII-safe text'
Write-Host '- processed preview now prefers normalized_path over ocr_ready_path'
Write-Host '- photo normalizer rejects near-full-frame background masks'

git diff -- frontend/src/features/receipts/KassaPage.jsx backend/app/api/receipt_preview_routes.py backend/app/domains/receipts/image/receipt_photo_normalizer.py

git add frontend/src/features/receipts/KassaPage.jsx backend/app/api/receipt_preview_routes.py backend/app/domains/receipts/image/receipt_photo_normalizer.py
git commit -m 'R9-34G fix Kassa mojibake and processed preview route'
git push

Write-Host 'R9-34G-FIX toegepast en gepusht.'
