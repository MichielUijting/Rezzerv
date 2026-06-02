from pathlib import Path

p = Path("backend/app/testing/receipt_status_baseline/expected_status_v7.json")
text = p.read_text(encoding="utf-8-sig")

old = '''    "source_file": "plus foto 1.jpg",
    "expected_parse_status": "approved",
    "expected_status_label": "Gecontroleerd",
    "store_name": "PLUS",
    "total_amount": 14.33,
    "currency": "EUR",
    "line_count": 10,
    "sum_line_total": 25.56,
    "net_line_total": 14.33,
    "discount_total": 11.23,
    "reason": "R9-38B11: productregelcount gecorrigeerd naar 10; kortingen en subtotal-correcties tellen niet mee als productregels",
'''

new = '''    "source_file": "plus foto 1.jpg",
    "expected_parse_status": "approved",
    "expected_status_label": "Gecontroleerd",
    "store_name": "PLUS",
    "total_amount": 14.33,
    "currency": "EUR",
    "line_count": 11,
    "sum_line_total": 25.56,
    "net_line_total": 14.33,
    "discount_total": 11.23,
    "reason": "R9-38B16: baseline hersteld naar 11 normregels; PLUS zegel/actiecorrectie telt mee als normregel zonder dubbele discount_total-telling",
'''

if old not in text:
    raise SystemExit("R9-38B16 baseline needle not found; paste plus foto 1 baseline block.")

text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8", newline="\n")
print("R9-38B16 baseline plus foto 1 restored to line_count 11")
