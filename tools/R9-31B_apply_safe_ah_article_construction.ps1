param([switch]$NoCommit)
$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-31B apply failed: verkeerde branch: $branch"
  exit 1
}

$python = @'
from pathlib import Path
path = Path('backend/app/services/receipt_service.py')
text = path.read_text(encoding='utf-8-sig')

import_line = "from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import apply_receipt_image_preprocessing\n"
new_import = import_line + "from app.receipt_ingestion.profiles.ah_runtime import build_ah_profile_article_lines\n"
if "build_ah_profile_article_lines" not in text:
    if import_line not in text:
        raise SystemExit('R9-31B apply failed: import-anchor niet gevonden')
    text = text.replace(import_line, new_import, 1)

anchor = """    lines = _filter_non_product_receipt_lines(lines)
    discount_total = _apply_discount_entries(lines, _extract_discount_entries(text_lines))
"""
insert = """    lines = _filter_non_product_receipt_lines(lines)
    ah_profile_lines = build_ah_profile_article_lines(
        text_lines,
        lines,
        store_name=store_name,
        filename=filename,
        append_product_candidate=append_product_candidate,
        clean_label=_clean_receipt_label,
        parse_quantity=_parse_quantity,
        parse_decimal=_parse_decimal,
        amount_to_float=_amount_to_float,
        classify_line=lambda value: _classify_receipt_text_line(
            value,
            store_name=store_name,
            filename=filename,
        ),
        is_invalid_label=_looks_like_non_product_receipt_label,
    )
    if ah_profile_lines:
        lines.extend(ah_profile_lines)
        lines.sort(key=lambda item: int(item.get('source_index') or 0))
        lines = _filter_non_product_receipt_lines(lines)
    discount_total = _apply_discount_entries(lines, _extract_discount_entries(text_lines))
"""
if "ah_profile_lines = build_ah_profile_article_lines" not in text:
    if anchor not in text:
        raise SystemExit('R9-31B apply failed: parser-anchor niet gevonden')
    text = text.replace(anchor, insert, 1)

path.write_text(text, encoding='utf-8')
print('R9-31B patch toegepast.')
'@

$python | python -

git diff -- backend/app/services/receipt_service.py

if (-not $NoCommit) {
  git add backend/app/services/receipt_service.py
  git commit -m 'R9-31B activate safe AH article construction'
  git push
  Write-Host 'R9-31B commit gepusht.'
} else {
  Write-Host 'NoCommit gebruikt; commit/push overgeslagen.'
}
