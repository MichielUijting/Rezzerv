from pathlib import Path

p = Path("backend/app/receipt_ingestion/service_parts/plus_photo_line_grouping_fallback.py")
text = p.read_text(encoding="utf-8-sig")

old = """    if not diagnostics['has_suspicious_article_merges']:
        diagnostics['fallback_reject_reason'] = 'no_suspicious_article_merges'
        return diagnostics
"""

new = """    if not diagnostics['has_suspicious_article_merges'] and not diagnostics['has_pluspunten_correction']:
        diagnostics['fallback_reject_reason'] = 'no_suspicious_article_merges_or_pluspunten_path'
        return diagnostics
"""

if old not in text:
    raise SystemExit("B14b guard needle not found. Stop and paste the diagnose_plus_photo_line_grouping_fallback block.")

text = text.replace(old, new, 1)

p.write_text(text, encoding="utf-8", newline="\n")
print("R9-38B14b guard patch applied")
