from pathlib import Path

p = Path(r"C:\Users\Gebruiker\Rezzerv_Github\backend\app\receipt_ingestion\preprocessing\receipt_image_preprocessing.py")
s = p.read_text(encoding="utf-8")

needle = """def apply_receipt_image_preprocessing(file_bytes: bytes, filename: str) -> tuple[bytes, ReceiptImagePreprocessingDecision]:
    suffix = Path(filename or "").suffix.lower()
"""

replacement = """def apply_receipt_image_preprocessing(file_bytes: bytes, filename: str) -> tuple[bytes, ReceiptImagePreprocessingDecision]:
    raise RuntimeError("R9-21H TRACE ACTIVE: apply_receipt_image_preprocessing was called")
    suffix = Path(filename or "").suffix.lower()
"""

if needle not in s:
    raise SystemExit("R9-21H patchpunt niet gevonden; niets aangepast.")

s = s.replace(needle, replacement, 1)
p.write_text(s, encoding="utf-8")
print("R9-21H trace actief gemaakt.")
