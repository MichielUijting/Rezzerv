from pathlib import Path

path = Path('backend/app/services/receipt_service.py')
text = path.read_text(encoding='utf-8')

old_import = 'from app.receipt_ingestion.profiles.ah_runtime import build_ah_profile_article_lines\n'
new_import = 'from app.receipt_ingestion.profiles.ah_runtime import build_ah_profile_article_lines, extract_positive_contributors\n'
if new_import not in text:
    if old_import not in text:
        raise SystemExit('R9-32G import anchor not found')
    text = text.replace(old_import, new_import, 1)

anchor = '    lines = _filter_non_product_receipt_lines(lines)\n    ah_profile_lines = build_ah_profile_article_lines(\n'
insert = '''    profile_positive_contributor_lines = extract_positive_contributors(
        text_lines,
        lines,
        store_name=store_name,
        filename=filename,
    )
    if profile_positive_contributor_lines:
        existing_positive_keys = {
            (
                str(line.get('raw_label') or line.get('normalized_label') or '').strip().lower(),
                str(line.get('line_total') or ''),
                str(line.get('source_index') or ''),
            )
            for line in lines
        }
        for contributor_line in profile_positive_contributor_lines:
            contributor_key = (
                str(contributor_line.get('raw_label') or contributor_line.get('normalized_label') or '').strip().lower(),
                str(contributor_line.get('line_total') or ''),
                str(contributor_line.get('source_index') or ''),
            )
            if contributor_key in existing_positive_keys:
                continue
            lines.append(contributor_line)
            existing_positive_keys.add(contributor_key)
        lines.sort(key=lambda item: int(item.get('source_index') or 0))
'''
if 'profile_positive_contributor_lines = extract_positive_contributors(' not in text:
    if anchor not in text:
        raise SystemExit('R9-32G flow anchor not found')
    text = text.replace(anchor, insert + anchor, 1)

path.write_text(text, encoding='utf-8')
print('R9-32G applied')
