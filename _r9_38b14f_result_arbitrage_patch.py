from pathlib import Path

p = Path("backend/app/services/receipt_service.py")
text = p.read_text(encoding="utf-8-sig")

needle_after_tesseract = """        tesseract_result = _parse_result_from_text_lines(
            tesseract_lines,
            filename,
            rich_confidence=0.82,
            partial_confidence=0.62,
            review_confidence=0.34,
        ) if tesseract_lines else _failed_receipt_result(0.0)
"""

insert_after_tesseract = needle_after_tesseract + """
        def _r9_38b14f_plus_subtotal_validated_fallback_lines(candidate_lines: list[str] | None) -> bool:
            # Guarded PLUS image fallback detection.
            # No receipt id / filename matching: only validates PLUS profile, article block,
            # subtotal math, and absence of payment lines in the product block.
            normalized_lines = [re.sub(r'\\s+', ' ', str(line or '')).strip() for line in (candidate_lines or []) if str(line or '').strip()]
            lowered_lines = [line.lower() for line in normalized_lines]
            if not any(line == 'plus' or line.startswith('plus ') for line in lowered_lines[:20]):
                return False
            if not any('pluspunten' in line or 'piuspunten' in line for line in lowered_lines):
                return False

            subtotal_index = next((idx for idx, line in enumerate(lowered_lines) if 'subtotaal' in line), None)
            if subtotal_index is None:
                return False

            start_index = 0
            for idx, line in enumerate(lowered_lines[:subtotal_index]):
                if 'omschrijving' in line or 'onschrijving' in line:
                    start_index = idx + 1

            payment_tokens = ('contactless', 'terminal', 'merchant', 'betaling', 'kaart', 'visa debit', 'pin ', 'wisselgeld')
            amount_re = re.compile(r'(?<!\\d)(\\d{1,5}[\\.,]\\d{2})(?!\\d)')
            article_amounts: list[Decimal] = []
            for line in normalized_lines[start_index:subtotal_index]:
                lowered = line.lower()
                if any(token in lowered for token in payment_tokens):
                    return False
                if not re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}', line):
                    continue
                amount_matches = amount_re.findall(line)
                if len(amount_matches) != 1:
                    continue
                amount = _parse_decimal(amount_matches[0])
                if amount is not None:
                    article_amounts.append(amount)

            if len(article_amounts) < 8:
                return False

            subtotal_window = ' '.join(normalized_lines[subtotal_index: min(len(normalized_lines), subtotal_index + 3)])
            subtotal_matches = amount_re.findall(subtotal_window)
            subtotal_values = [_parse_decimal(value) for value in subtotal_matches]
            subtotal_values = [value for value in subtotal_values if value is not None]
            if not subtotal_values:
                return False

            article_sum = sum(article_amounts, Decimal('0'))
            if not any(abs(article_sum - subtotal_value) <= Decimal('0.02') for subtotal_value in subtotal_values):
                return False

            return True

        plus_safe_rotation_fallback_lines = bool(
            safe_rotation_decision
            and getattr(safe_rotation_decision, 'selected_route', None) != 'original'
            and _r9_38b14f_plus_subtotal_validated_fallback_lines(paddle_lines)
        )
"""

if "def _r9_38b14f_plus_subtotal_validated_fallback_lines" not in text:
    if needle_after_tesseract not in text:
        raise SystemExit("B14f tesseract_result needle not found.")
    text = text.replace(needle_after_tesseract, insert_after_tesseract, 1)

old_image_choice = """        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        if ah_paddle_merged_product_line and tesseract_result.is_receipt:
            image_result = tesseract_result
"""

new_image_choice = """        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        if ah_paddle_merged_product_line and tesseract_result.is_receipt:
            image_result = tesseract_result
        if plus_safe_rotation_fallback_lines:
            image_result = paddle_result
"""

if "if plus_safe_rotation_fallback_lines:\n            image_result = paddle_result" not in text:
    if old_image_choice not in text:
        raise SystemExit("B14f image_result needle not found.")
    text = text.replace(old_image_choice, new_image_choice, 1)

old_best_choice = """            best_result = _choose_better_receipt_result(image_result, original_result)
            if ah_force_preprocessed_tesseract:
                best_result = image_result
"""

new_best_choice = """            best_result = _choose_better_receipt_result(image_result, original_result)
            if ah_force_preprocessed_tesseract or plus_safe_rotation_fallback_lines:
                best_result = image_result
"""

if "if ah_force_preprocessed_tesseract or plus_safe_rotation_fallback_lines:" not in text:
    if old_best_choice not in text:
        raise SystemExit("B14f best_result needle not found.")
    text = text.replace(old_best_choice, new_best_choice, 1)

p.write_text(text, encoding="utf-8", newline="\n")
print("R9-38B14f result-arbitrage patch applied")
