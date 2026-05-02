import re
from pathlib import Path

# --- FILE 1: baseline service ---
p1 = Path('backend/app/services/receipt_status_baseline_service_v4.py')
s = p1.read_text(encoding='utf-8')

if '_normalize_filename' not in s:
    s = s.replace('import re', 'import re\n\n\ndef _normalize_filename(value: str | None) -> str:\n    if not value:\n        return ""\n    v = str(value).strip().lower()\n    v = v.replace(".jpeg", ".jpg")\n    v = re.sub(r"\\s+", " ", v)\n    return v\n')

s = s.replace("b['source_file'] == r['source_file']", "_normalize_filename(b['source_file']) == _normalize_filename(r['source_file'])")
s = s.replace("str(actual.get('source_file') or '') == str(expected.get('source_file') or '')", "_normalize_filename(actual.get('source_file')) == _normalize_filename(expected.get('source_file'))")

p1.write_text(s, encoding='utf-8')

# --- FILE 2: parser ---
p2 = Path('backend/app/services/receipt_service.py')
s2 = p2.read_text(encoding='utf-8')

if '_canonicalize_store' not in s2:
    insert = '''\n\ndef _canonicalize_store(store: str | None, text: str, filename: str) -> str | None:\n    if not store:\n        return None\n    s = store.lower()\n    text_l = text.lower()\n    file_l = filename.lower()\n    if s == "plus":\n        return "PLUS"\n    if s == "lidl":\n        if "arnhem" in text_l or "arnhem" in file_l:\n            return "Lidl Arnhem"\n        if "gmbh" in text_l:\n            return "Lidl Nederland GmbH"\n        return "Lidl"\n    if s == "jumbo":\n        if "heteren" in text_l:\n            return "Jumbo Heteren Teun van Blijderveen"\n        if "oude pekela" in text_l:\n            return "Jumbo Oude Pekela"\n        if "supermarkten" in text_l:\n            return "Jumbo Supermarkten"\n        return "Jumbo"\n    return store\n'''
    s2 = s2 + insert

s2 = s2.replace("return normalized_store", "return _canonicalize_store(normalized_store, haystack, filename)")

p2.write_text(s2, encoding='utf-8')

# cleanup workflow
try:\n    Path('.github/workflows/apply-pr3.yml').unlink()\n    Path('tools/apply_pr3_normalization.py').unlink()\nexcept Exception:\n    pass
