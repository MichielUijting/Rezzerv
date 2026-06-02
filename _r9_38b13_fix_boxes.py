from pathlib import Path

p = Path("backend/app/testing/r9_38b13_plus_photo2_ocr_fragments.py")
text = p.read_text(encoding="utf-8-sig")

old = '        boxes = pay.get("rec_boxes") or pay.get("dt_polys") or pay.get("rec_polys") or []\n'

new = '''        boxes = pay.get("rec_boxes")
        if boxes is None:
            boxes = pay.get("dt_polys")
        if boxes is None:
            boxes = pay.get("rec_polys")
        if boxes is None:
            boxes = []
'''

if old not in text:
    raise SystemExit("Needle not found; paste the relevant run_ocr block.")

text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8", newline="\n")
print("R9-38B13 numpy-array boxes fix applied")
