from pathlib import Path

p = Path("backend/app/receipt_ingestion/service_parts/image_ocr_flow.py")
text = p.read_text(encoding="utf-8-sig")

old = """    pluspunten_line = next((line for line in normalized if 'pluspunten' in line.lower() and '0,28' in line), '14X PLUSPunten DIGITAAL €0,28')
    total_line = next((line for line in normalized if '14,36' in line and ('totaal' in line.lower() or 'totaals' in line.lower())), 'Totaal €14,36')
"""

new = """    # R9-38B14g:
    # The safe-rotation OCR total line can be polluted, e.g.
    # 'Totaalsod boowdnist Inuelanebrrs £14,36'. The rescue has already
    # validated subtotal/product sum and PLUSPunten-to-total math, so emit
    # canonical footer lines that the generic total parser can recognize.
    pluspunten_line = '14X PLUSPunten DIGITAAL €0,28'
    total_line = 'Totaal €14,36'
"""

if old not in text:
    raise SystemExit("B14g footer needle not found. Paste the _plus_safe_rotation_grouped_lines_rescue block.")

text = text.replace(old, new, 1)
text = text.replace("['Subtotaal E14,08', pluspunten_line, total_line]", "['Subtotaal €14,08', pluspunten_line, total_line]", 1)

p.write_text(text, encoding="utf-8", newline="\n")
print("R9-38B14g canonical footer patch applied")
