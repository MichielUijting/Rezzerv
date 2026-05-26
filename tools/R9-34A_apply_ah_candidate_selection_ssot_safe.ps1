$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-34A apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/receipt_ingestion/profiles/ah_runtime.py')
text = path.read_text(encoding='utf-8')

if 'AH_CANDIDATE_SELECTION_BRANCH' not in text:
    anchor = "POSITIVE_CONTRIBUTOR_BRANCH = 'positive_savings_contribution'\n"
    if anchor not in text:
        raise SystemExit('R9-34A failed: AH constant anchor not found')
    text = text.replace(anchor, anchor + "AH_CANDIDATE_SELECTION_BRANCH = 'ah_candidate_selection_ssot_safe'\n", 1)

helper_marker = 'def _extract_amounts(line: str) -> list[Decimal]:\n'
helper_block = r'''

def _ah_candidate_selection_reason(line: str | None) -> dict[str, Any]:
    """SSOT-safe AH line selection helper.

    This helper only marks AH product/non-product candidate evidence. It must never set
    receipt status, parser status, po_norm_status_label, or UI category fields.
    """
    raw = str(line or '').strip()
    norm = _norm(raw)
    non_product_reasons: list[str] = []

    if not raw:
        return {
            'ah_candidate_selection_branch': AH_CANDIDATE_SELECTION_BRANCH,
            'is_ah_product_candidate': False,
            'is_ah_non_product_candidate': False,
            'ah_candidate_reasons': [],
            'ah_non_product_reasons': ['empty_line'],
        }

    if any(token in norm for token in ('subtotaal', 'totaal', 'te betalen', 'betalen')):
        non_product_reasons.append('ah_total_or_payment_total_line')
    if any(token in norm for token in ('pinnen', 'pin ', 'v pay', 'v-pay', 'betaling', 'betaald met')):
        non_product_reasons.append('ah_payment_line')
    if any(token in norm for token in ('app deals', 'bonus', 'voordeel', 'korting')):
        non_product_reasons.append('ah_promotion_or_advantage_line')
    if any(token in norm for token in ('btw', 'over', 'eur')) and len(_extract_amounts(raw)) >= 2:
        non_product_reasons.append('ah_vat_or_tax_line')
    if any(token in norm for token in ('terminal', 'merchant', 'transactie', 'kaart', 'autorisatiecode', 'klantticket', 'poi:')):
        non_product_reasons.append('ah_payment_terminal_metadata')
    if any(token in norm for token in ('download nu de ah', 'spaar automatisch', 'gratis een product')):
        non_product_reasons.append('ah_footer_marketing_line')

    amounts = _extract_amounts(raw)
    has_amount = bool(amounts)
    has_letters = any(ch.isalpha() for ch in raw)
    has_non_product_reason = bool(non_product_reasons)
    is_product = has_amount and has_letters and not has_non_product_reason

    reasons: list[str] = []
    if is_product:
        reasons.append('ah_amount_bearing_text_line_without_non_product_signal')

    return {
        'ah_candidate_selection_branch': AH_CANDIDATE_SELECTION_BRANCH,
        'is_ah_product_candidate': is_product,
        'is_ah_non_product_candidate': has_non_product_reason,
        'ah_candidate_reasons': reasons,
        'ah_non_product_reasons': sorted(set(non_product_reasons)),
    }


def enrich_ah_amount_line_candidates(candidates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return AH candidate evidence without changing receipt status or generic parser output."""
    enriched: list[dict[str, Any]] = []
    for candidate in candidates or []:
        item = dict(candidate)
        line = item.get('normalized_line') or item.get('raw_line') or ''
        item.update(_ah_candidate_selection_reason(line))
        item['status_classification_applied'] = False
        item['po_norm_status_label_touched'] = False
        enriched.append(item)
    return enriched
'''
if 'def _ah_candidate_selection_reason(' not in text:
    if helper_marker not in text:
        raise SystemExit('R9-34A failed: helper insertion anchor not found')
    text = text.replace(helper_marker, helper_block + '\n' + helper_marker, 1)

# Add optional hook in existing AH refine function if a generic metadata/candidate payload is present.
# This is intentionally defensive: it only enriches diagnostic candidate lists and leaves product lines/status untouched.
if 'enrich_ah_amount_line_candidates(' not in text.split('def enrich_ah_amount_line_candidates', 1)[-1]:
    pass

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('R9-34A applied: AH SSOT-safe candidate selection helpers added')
'@

$py | python -
if ($LASTEXITCODE -ne 0) {
  Write-Error "R9-34A failed: Python patch failed"
  exit 1
}

git --no-pager diff -- backend/app/receipt_ingestion/profiles/ah_runtime.py

git add backend/app/receipt_ingestion/profiles/ah_runtime.py
git commit -m 'R9-34A add SSOT-safe AH candidate selection helpers'
git push

Write-Host 'R9-34A toegepast en gepusht.'
