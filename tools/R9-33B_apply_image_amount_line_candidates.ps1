$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-33B apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/testing_receipt_line_diagnosis_routes.py')
text = path.read_text(encoding='utf-8')

if 'import re\n' not in text:
    text = text.replace('import json\n', 'import json\nimport re\n', 1)

helper_anchor = "def _line_summary(lines: list[str]) -> dict[str, Any]:\n"
helper_block = r'''

AMOUNT_LINE_PATTERN = re.compile(
    r'(?<![A-Za-z0-9])(?:[€£$]|EUR|E|C)?\s*-?\d{1,6}(?:[\.,]\d{2})(?!\d)',
    re.IGNORECASE,
)
COMPACT_AMOUNT_LINE_PATTERN = re.compile(
    r'(?<![A-Za-z0-9])\d+\s*[xX]\s*\d{1,6}(?:[\.,]\d{2})\s+\d{1,6}(?:[\.,]\d{2})(?!\d)',
    re.IGNORECASE,
)


def _normalize_ocr_amount_token(value: str | None) -> str:
    token = re.sub(r'\s+', '', str(value or '').strip())
    token = re.sub(r'^(?:EUR|€|E|C|£|\$)', '', token, flags=re.IGNORECASE)
    return token


def _extract_ocr_amounts(line: str | None) -> list[str]:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    amounts = [_normalize_ocr_amount_token(match.group(0)) for match in AMOUNT_LINE_PATTERN.finditer(normalized)]
    return [amount for amount in amounts if amount]


def _build_amount_line_candidates(engine_name: str, raw_lines: list[str] | None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, raw_line in enumerate(raw_lines or []):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        if not normalized:
            continue
        amounts = _extract_ocr_amounts(normalized)
        compact_match = bool(COMPACT_AMOUNT_LINE_PATTERN.search(normalized))
        if not amounts and not compact_match:
            continue
        candidates.append({
            'source_engine': engine_name,
            'source_line_index': index,
            'raw_line': raw_line,
            'normalized_line': normalized,
            'amounts_detected': amounts,
            'last_amount': amounts[-1] if amounts else None,
            'candidate_type_unclassified': True,
            'classification_applied': False,
            'store_filtering_applied': False,
            'reason': 'amount_pattern_detected_before_store_filtering',
        })
    return candidates


def _ocr_amount_line_candidate_summary(paddle_lines: list[str] | None, tesseract_lines: list[str] | None) -> dict[str, Any]:
    paddle_candidates = _build_amount_line_candidates('paddle', paddle_lines)
    tesseract_candidates = _build_amount_line_candidates('tesseract', tesseract_lines)
    all_candidates = paddle_candidates + tesseract_candidates
    return {
        'count': len(all_candidates),
        'paddle_count': len(paddle_candidates),
        'tesseract_count': len(tesseract_candidates),
        'candidates': all_candidates,
        'truncated': False,
        'scope': 'image_ocr_amount_lines_before_parser_and_store_filtering',
    }
'''
if 'AMOUNT_LINE_PATTERN = re.compile(' not in text:
    if helper_anchor not in text:
        raise SystemExit('R9-33B helper anchor not found')
    text = text.replace(helper_anchor, helper_block + '\n' + helper_anchor, 1)

old = """            return {
                **base_payload,
                'source_kind': 'image',
                'image_preprocessing_before_ocr': preprocessing,
                'paddle_ocr_text': {
                    'available': bool(paddle_lines),
                    'confidence': paddle_confidence,
                    'raw_lines': _line_summary(paddle_lines),
                },
                'tesseract_ocr_text': {
                    'available': bool(tesseract_lines),
                    'confidence': tesseract_confidence,
                    'raw_lines': _line_summary(tesseract_lines),
                },
                'parser_preprocessing_not_applied_here': True,
                'duration_ms': _elapsed_ms(start),
            }
"""
new = """            amount_line_candidates = _ocr_amount_line_candidate_summary(paddle_lines, tesseract_lines)
            return {
                **base_payload,
                'source_kind': 'image',
                'image_preprocessing_before_ocr': preprocessing,
                'paddle_ocr_text': {
                    'available': bool(paddle_lines),
                    'confidence': paddle_confidence,
                    'raw_lines': _line_summary(paddle_lines),
                },
                'tesseract_ocr_text': {
                    'available': bool(tesseract_lines),
                    'confidence': tesseract_confidence,
                    'raw_lines': _line_summary(tesseract_lines),
                },
                'ocr_amount_line_candidates': amount_line_candidates,
                'parser_preprocessing_not_applied_here': True,
                'duration_ms': _elapsed_ms(start),
            }
"""
if "'ocr_amount_line_candidates': amount_line_candidates" not in text:
    if old not in text:
        raise SystemExit('R9-33B image return anchor not found')
    text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
print('R9-33B applied: image OCR amount-line candidates added to source-text report')
'@

$py | python -

git --no-pager diff -- backend/app/testing_receipt_line_diagnosis_routes.py

git add backend/app/testing_receipt_line_diagnosis_routes.py
git commit -m 'R9-33B add image OCR amount-line candidates'
git push

Write-Host 'R9-33B toegepast en gepusht.'
