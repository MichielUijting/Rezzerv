from pathlib import Path

root = Path(r"C:\Users\Gebruiker\Rezzerv_Github")
pre = root / "backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py"
dbg = root / "tools/R9-21A_export_receipt_preprocessing.py"

s = pre.read_text(encoding="utf-8")
s = s.replace(
    '    raise RuntimeError("R9-21H TRACE ACTIVE: apply_receipt_image_preprocessing was called")\n',
    "",
)
pre.write_text(s, encoding="utf-8")

d = dbg.read_text(encoding="utf-8")

if "from app.receipt_ingestion.preprocessing import receipt_image_preprocessing as runtime_pre" not in d:
    d = d.replace(
        "from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import apply_receipt_image_preprocessing\n",
        "from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import apply_receipt_image_preprocessing\n"
        "from app.receipt_ingestion.preprocessing import receipt_image_preprocessing as runtime_pre\n",
    )

old = """    runtime_bytes, runtime_decision = apply_receipt_image_preprocessing(data, filename)
    runtime_image = Image.open(io.BytesIO(runtime_bytes)).convert('RGB')
    _save_pil(runtime_image, case_dir / '03_runtime_preprocessed.png')
"""

new = """    # R9-21H: export runtime contour diagnostics from the exact same preprocessing module.
    if runtime_pre.cv2 is not None and runtime_pre.np is not None:
        original_arr = runtime_pre._decode_image(data)
        if original_arr is not None:
            height, width = original_arr.shape[:2]
            ratio = height / 900.0 if height > 900 else 1.0
            small = runtime_pre.cv2.resize(original_arr, (int(width / ratio), int(height / ratio)))
            gray_arr = runtime_pre.cv2.cvtColor(small, runtime_pre.cv2.COLOR_BGR2GRAY)
            gray_arr = runtime_pre.cv2.bilateralFilter(gray_arr, 9, 75, 75)
            edges = runtime_pre.cv2.Canny(gray_arr, 35, 110)
            edges = runtime_pre.cv2.dilate(edges, runtime_pre.np.ones((5, 5), runtime_pre.np.uint8), iterations=2)
            edges = runtime_pre.cv2.morphologyEx(edges, runtime_pre.cv2.MORPH_CLOSE, runtime_pre.np.ones((9, 9), runtime_pre.np.uint8), iterations=2)

            edges_big = runtime_pre.cv2.resize(edges, (width, height))
            _save_pil(Image.fromarray(edges_big), case_dir / '02_edges.png')

            overlay = original_arr.copy()
            contours, _ = runtime_pre.cv2.findContours(edges, runtime_pre.cv2.RETR_EXTERNAL, runtime_pre.cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=runtime_pre.cv2.contourArea, reverse=True)[:20]
            scaled_contours = [(cnt.astype('float32') * ratio).astype('int32') for cnt in contours]
            runtime_pre.cv2.drawContours(overlay, scaled_contours, -1, (0, 255, 0), 3)

            quad = runtime_pre._find_document_quadrilateral(original_arr)
            if quad is not None:
                runtime_pre.cv2.polylines(overlay, [quad.astype('int32')], True, (0, 0, 255), 8)

            overlay_rgb = runtime_pre.cv2.cvtColor(overlay, runtime_pre.cv2.COLOR_BGR2RGB)
            _save_pil(Image.fromarray(overlay_rgb), case_dir / '02_contour_overlay.png')

    runtime_bytes, runtime_decision = apply_receipt_image_preprocessing(data, filename)
    runtime_image = Image.open(io.BytesIO(runtime_bytes)).convert('RGB')
    _save_pil(runtime_image, case_dir / '03_runtime_preprocessed.png')
"""

if old not in d:
    raise SystemExit("Debug-export patchpunt niet gevonden; niets aangepast.")

d = d.replace(old, new, 1)
dbg.write_text(d, encoding="utf-8")

print("R9-21H vervolg toegepast: trace verwijderd en contour-debug toegevoegd.")
