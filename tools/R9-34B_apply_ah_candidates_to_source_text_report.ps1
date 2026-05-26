$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-34B apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/testing_receipt_line_diagnosis_routes.py')
text = path.read_text(encoding='utf-8')

anchor = 'def _ocr_amount_line_candidate_summary(paddle_lines: list[str] | None, tesseract_lines: list[str] | None) -> dict[str, Any]:\n'
block = r'''

def _maybe_enrich_ah_candidate_summary(amount_line_candidates: dict[str, Any], *, store_name: str | None, store_chain: str | None, text_lines: list[str]) -> dict[str, Any]:
    try:
        from app.receipt_ingestion.profiles.ah_runtime import _looks_like_ah_context, enrich_ah_amount_line_candidates
    except Exception:
        return amount_line_candidates

    if not _looks_like_ah_context(store_name or store_chain, text_lines):
        return amount_line_candidates

    enriched = dict(amount_line_candidates or {})
    candidates = enrich_ah_amount_line_candidates(enriched.get('candidates') or [])
    duplicates = enrich_ah_amount_line_candidates(enriched.get('duplicates') or [])
    enriched['candidates'] = candidates
    enriched['duplicates'] = duplicates
    enriched['ah_candidate_selection'] = {
        'applied': True,
        'scope': 'ah_profile_read_only_candidate_diagnostics',
        'ssot_safe': True,
        'status_classification_applied': False,
        'po_norm_status_label_touched': False,
        'store_filtering_effect_on_other_chains': False,
        'product_candidate_count': sum(1 for item in candidates if item.get('is_ah_product_candidate')),
        'non_product_candidate_count': sum(1 for item in candidates if item.get('is_ah_non_product_candidate')),
    }
    enriched['ah_product_candidate_count'] = enriched['ah_candidate_selection']['product_candidate_count']
    enriched['ah_non_product_candidate_count'] = enriched['ah_candidate_selection']['non_product_candidate_count']
    return enriched
'''
if '_maybe_enrich_ah_candidate_summary(' not in text:
    if anchor not in text:
        raise SystemExit('R9-34B failed: helper anchor not found')
    text = text.replace(anchor, block + '\n' + anchor, 1)

old = """            amount_line_candidates = _ocr_amount_line_candidate_summary(paddle_lines, tesseract_lines)
            return {
                **base_payload,
                'source_kind': 'image',
"""
new = """            amount_line_candidates = _ocr_amount_line_candidate_summary(paddle_lines, tesseract_lines)
            amount_line_candidates = _maybe_enrich_ah_candidate_summary(
                amount_line_candidates,
                store_name=str(row.get('store_name') or ''),
                store_chain=str(row.get('store_chain') or ''),
                text_lines=list(paddle_lines or []) + list(tesseract_lines or []),
            )
            return {
                **base_payload,
                'source_kind': 'image',
"""
if "amount_line_candidates = _maybe_enrich_ah_candidate_summary(" not in text:
    if old not in text:
        raise SystemExit('R9-34B failed: image amount candidate anchor not found')
    text = text.replace(old, new, 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('R9-34B applied')
'@

$py | python -
if ($LASTEXITCODE -ne 0) { exit 1 }

git --no-pager diff -- backend/app/testing_receipt_line_diagnosis_routes.py
git add backend/app/testing_receipt_line_diagnosis_routes.py
git commit -m 'R9-34B connect AH candidates to source text report'
git push
Write-Host 'R9-34B toegepast en gepusht.'
