from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'api' / 'receipt_import_diagnosis_routes.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r6d')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

replacements = {
    "'should_be_manual': 0": "'should_need_review': 0",
    'should_be_manual = not has_store or not has_total or line_count == 0': 'should_need_review = not has_store or not has_total or line_count == 0',
    "'expected_behavior': 'create_manual_receipt_when_parse_quality_low' if should_be_manual else 'create_receipt_table_and_apply_existing_status_flow'": "'expected_behavior': 'create_review_needed_receipt_when_parse_quality_low' if should_need_review else 'create_receipt_table_and_apply_existing_status_flow'",
    "'should_be_manual': sum(1 for item in items if item.get('expected_behavior') == 'create_manual_receipt_when_parse_quality_low')": "'should_need_review': sum(1 for item in items if item.get('expected_behavior') == 'create_review_needed_receipt_when_parse_quality_low')",
    'Technisch leesbare supermarktbonnen moeten zichtbaar worden in Kassa als Gecontroleerd, Controle nodig of Handmatig. Alleen corrupte/unsupported bestanden horen technisch mislukt te zijn.': 'Technisch leesbare supermarktbonnen moeten zichtbaar worden in Kassa als Gecontroleerd of Controle nodig. Alleen corrupte/unsupported bestanden horen technisch mislukt te zijn.',
    'Als dit een supermarktbon is, moet de importflow minimaal een Handmatig-bon aanmaken.': 'Als dit een supermarktbon is, moet de importflow minimaal een bon met Controle nodig aanmaken.',
}

for old, new in replacements.items():
    if old not in content:
        raise SystemExit(f'R6d patch aborted: expected text not found: {old!r}')
    content = content.replace(old, new)

for forbidden in ['should_be_manual', 'create_manual_receipt_when_parse_quality_low', 'Handmatig']:
    if forbidden in content:
        raise SystemExit(f'R6d guard failed: {forbidden!r} still present in diagnosis route.')

TARGET.write_text(content, encoding='utf-8')
print('R6d diagnosis manual cleanup patch applied to', TARGET)
print('Backup written to', BACKUP)
