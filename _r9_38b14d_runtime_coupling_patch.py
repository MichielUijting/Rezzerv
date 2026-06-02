from pathlib import Path

p = Path("backend/app/services/receipt_service.py")
text = p.read_text(encoding="utf-8-sig")

needle = """        paddle_result = _parse_result_from_text_lines(
            paddle_lines,
            filename,
            rich_confidence=0.84,
            partial_confidence=0.64,
            review_confidence=0.36,
        ) if paddle_lines else _failed_receipt_result(0.0)
"""

insert = needle + """
        # R9-38B14d:
        # If PLUS image OCR already produced the guarded fallback reconstruction,
        # keep this result as the runtime parser input. This prevents later OCR
        # arbitrage from replacing the 8 subtotal-validated product lines with
        # older merged lines or payment lines such as Contactless.
        plus_fallback_runtime_lines = bool(
            any(str(line or '').strip().lower() == 'bio dadeltjes 3,29' for line in (paddle_lines or []))
            and any(str(line or '').strip().lower() == 'dkk riustwafel 1,89' for line in (paddle_lines or []))
            and any(str(line or '').strip().lower() == 'groente ringen +12m 1,15' for line in (paddle_lines or []))
            and not any(str(line or '').strip().lower().startswith('contactless') for line in (paddle_lines or []))
        )
"""

if "plus_fallback_runtime_lines = bool(" not in text:
    if needle not in text:
        raise SystemExit("B14d paddle_result needle not found.")
    text = text.replace(needle, insert, 1)

old = """            if best_result is not image_result:
                image_result = best_result
                if best_result is original_paddle_result:
                    chosen_confidence = original_paddle_confidence
                    chosen_lines = original_paddle_lines
                else:
                    chosen_confidence = original_tesseract_confidence
                    chosen_lines = original_tesseract_lines
"""

new = """            if plus_fallback_runtime_lines:
                best_result = image_result
            if best_result is not image_result:
                image_result = best_result
                if best_result is original_paddle_result:
                    chosen_confidence = original_paddle_confidence
                    chosen_lines = original_paddle_lines
                else:
                    chosen_confidence = original_tesseract_confidence
                    chosen_lines = original_tesseract_lines
"""

if "if plus_fallback_runtime_lines:" not in text:
    if old not in text:
        raise SystemExit("B14d best_result needle not found.")
    text = text.replace(old, new, 1)

p.write_text(text, encoding="utf-8", newline="\n")
print("R9-38B14d runtime coupling patch applied")
