from pathlib import Path

root = Path(r"C:\Users\Gebruiker\Rezzerv_Github")
tool = root / "tools/R9-28B5_export_pre_parser_ocr_diagnostics.py"

text = tool.read_text(encoding="utf-8")

old = """                rec_texts = collection.get("rec_texts") or collection.get("texts") or []
                rec_scores = collection.get("rec_scores") or collection.get("scores") or []
                rec_boxes = collection.get("rec_boxes") or collection.get("boxes") or collection.get("dt_polys") or []
                for idx, text in enumerate(rec_texts):
                    value = str(text).strip()
                    if not value:
                        continue
                    texts.append(value)
                    confidences.append(_safe_float(rec_scores[idx]) if idx < len(rec_scores) else None)
                    boxes.append(rec_boxes[idx] if idx < len(rec_boxes) else None)
                continue
"""

new = """                def _first_present(mapping, keys):
                    for key in keys:
                        value = mapping.get(key)
                        if value is not None:
                            return value
                    return []

                def _safe_len(value):
                    try:
                        return len(value)
                    except Exception:
                        return 0

                def _safe_index(value, idx):
                    try:
                        if value is None:
                            return None
                        if idx >= _safe_len(value):
                            return None
                        item = value[idx]
                        if hasattr(item, "tolist"):
                            return item.tolist()
                        return item
                    except Exception:
                        return None

                rec_texts = _first_present(collection, ["rec_texts", "texts"])
                rec_scores = _first_present(collection, ["rec_scores", "scores"])
                rec_boxes = _first_present(collection, ["rec_boxes", "boxes", "dt_polys"])

                if hasattr(rec_texts, "tolist"):
                    rec_texts = rec_texts.tolist()
                if hasattr(rec_scores, "tolist"):
                    rec_scores = rec_scores.tolist()
                if hasattr(rec_boxes, "tolist"):
                    rec_boxes = rec_boxes.tolist()

                for idx, text in enumerate(rec_texts or []):
                    value = str(text).strip()
                    if not value:
                        continue
                    texts.append(value)
                    confidences.append(_safe_float(_safe_index(rec_scores, idx)))
                    boxes.append(_safe_index(rec_boxes, idx))
                continue
"""

if old not in text:
    raise SystemExit("Patchpunt niet gevonden. Controleer of R9-28B5_export_pre_parser_ocr_diagnostics.py exact de vorige versie is.")

tool.write_text(text.replace(old, new), encoding="utf-8")

print("R9-28B5A toegepast: NumPy-array veilige verwerking van PaddleOCR rec_boxes/rec_texts/rec_scores.")
print("Geen parser-, OCR-engine-, database-, status-, baseline- of UI-wijzigingen.")
print("Aangepast:")
print("- tools/R9-28B5_export_pre_parser_ocr_diagnostics.py")
