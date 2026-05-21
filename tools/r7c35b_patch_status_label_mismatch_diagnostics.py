from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / 'backend' / 'app' / 'services' / 'receipt_status_baseline_service.py'
s = p.read_text(encoding='utf-8')

old = """        if actual_status == expected_status and difference_type is None:\n            counts['correct'] += 1\n            result = 'correct'\n            reason = 'Actuele backendstatus komt overeen met de baseline.'\n        else:\n            counts['different'] += 1\n            result = 'different'\n            reason = 'Actuele backendstatus wijkt af van de baseline.'\n            if difference_type:\n                counts[difference_type] += 1\n"""
new = """        if actual_status == expected_status and difference_type is None:\n            counts['correct'] += 1\n            result = 'correct'\n            reason = 'Actuele backendstatus komt overeen met de baseline.'\n        else:\n            counts['different'] += 1\n            result = 'different'\n            reason = 'Actuele backendstatus wijkt af van de baseline.'\n            if difference_type is None:\n                difference_type = 'status_label_mismatch'\n                difference_reason = 'statuslabel wijkt af terwijl mapping en extractie niet als mismatch zijn geclassificeerd'\n            counts[difference_type] += 1\n"""
if old not in s:
    raise SystemExit('R7c35b patchpunt voor different zonder difference_type niet gevonden')
s = s.replace(old, new)

old_summary = """        'status_logic_mismatch': counts['status_logic_mismatch'],\n    }\n"""
new_summary = """        'status_logic_mismatch': counts['status_logic_mismatch'],\n        'status_label_mismatch': counts['status_label_mismatch'],\n    }\n"""
if old_summary not in s:
    raise SystemExit('R7c35b summary patchpunt niet gevonden')
s = s.replace(old_summary, new_summary)

old_diag_init = """    status_logic_mismatches = []\n    for item in details:\n"""
new_diag_init = """    status_logic_mismatches = []\n    status_label_mismatches = []\n    for item in details:\n"""
if old_diag_init not in s:
    raise SystemExit('R7c35b diagnose init patchpunt niet gevonden')
s = s.replace(old_diag_init, new_diag_init)

old_branch = """        elif item.get('difference_type') == 'status_logic_mismatch':\n            status_logic_mismatches.append({\n                **base,\n                'diagnosis': item.get('status_reason') or item.get('difference_reason'),\n                'identify_as_status_logic_mismatch': True,\n            })\n"""
new_branch = """        elif item.get('difference_type') == 'status_logic_mismatch':\n            status_logic_mismatches.append({\n                **base,\n                'diagnosis': item.get('status_reason') or item.get('difference_reason'),\n                'identify_as_status_logic_mismatch': True,\n            })\n        elif item.get('difference_type') == 'status_label_mismatch':\n            status_label_mismatches.append({\n                **base,\n                'diagnosis': item.get('difference_reason') or 'statuslabel wijkt af zonder extraction- of mappingmismatch',\n                'identify_as_status_label_mismatch': True,\n                'line_diagnostics': _build_extraction_diagnostics(conn, str(item.get('source_file') or ''), str(item.get('receipt_table_id') or '')),\n            })\n"""
if old_branch not in s:
    raise SystemExit('R7c35b diagnose branch patchpunt niet gevonden')
s = s.replace(old_branch, new_branch)

old_return = """        'status_logic_mismatch_count': len(status_logic_mismatches),\n        'extra_receipts': extra_receipts,\n        'mapping_mismatches': mapping_mismatches,\n        'extraction_mismatches': extraction_mismatches,\n        'status_logic_mismatches': status_logic_mismatches,\n"""
new_return = """        'status_logic_mismatch_count': len(status_logic_mismatches),\n        'status_label_mismatch_count': len(status_label_mismatches),\n        'extra_receipts': extra_receipts,\n        'mapping_mismatches': mapping_mismatches,\n        'extraction_mismatches': extraction_mismatches,\n        'status_logic_mismatches': status_logic_mismatches,\n        'status_label_mismatches': status_label_mismatches,\n"""
if old_return not in s:
    raise SystemExit('R7c35b diagnose return patchpunt niet gevonden')
s = s.replace(old_return, new_return)

p.write_text(s, encoding='utf-8')
print('R7c35b toegepast: different zonder difference_type krijgt status_label_mismatch diagnose')
