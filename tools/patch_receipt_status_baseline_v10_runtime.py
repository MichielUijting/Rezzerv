from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "backend" / "app" / "services" / "receipt_status_baseline_service.py"

text = SERVICE_PATH.read_text(encoding="utf-8")
original = text

old_helper = """def _normalize_baseline_source_file(value: Any) -> str:\n    text_value = _normalize_text(value)\n    while text_value.endswith('.eml.eml'):\n        text_value = text_value[:-4]\n    return text_value\n"""
new_helper = """def _normalize_baseline_source_file(value: Any) -> str:\n    raw_value = str(value or '').strip().lower()\n    while raw_value.endswith('.eml.eml'):\n        raw_value = raw_value[:-4]\n    return _normalize_text(raw_value)\n"""

if old_helper not in text:
    raise SystemExit("Kon _normalize_baseline_source_file blok niet eenduidig vinden")
text = text.replace(old_helper, new_helper, 1)

text = text.replace(
    "active_files = {_normalize_text(row.get('original_filename')) for row in actual_rows if row.get('original_filename')}",
    "active_files = {_normalize_baseline_source_file(row.get('original_filename')) for row in actual_rows if row.get('original_filename')}",
    1,
)
text = text.replace(
    "scoped = [row for row in expected_rows if _normalize_text(row.get('source_file')) in active_files]",
    "scoped = [row for row in expected_rows if _normalize_baseline_source_file(row.get('source_file')) in active_files]",
    1,
)

required = [
    "while raw_value.endswith('.eml.eml'):",
    "_normalize_baseline_source_file(row.get('original_filename'))",
    "_normalize_baseline_source_file(row.get('source_file')) in active_files",
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit("Patch incompleet; ontbreekt: " + ", ".join(missing))

if text == original:
    raise SystemExit("Geen wijzigingen aangebracht")

SERVICE_PATH.write_text(text, encoding="utf-8")
print("OK: V10 source_file normalisatie hersteld voor .eml.eml matching")
