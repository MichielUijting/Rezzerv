from pathlib import Path
import re

path = Path("backend/app/services/receipt_service.py")
text = path.read_text(encoding="utf-8-sig")
original = text

old_selection = """        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
        chosen_lines = paddle_lines if image_result is paddle_result else tesseract_lines
"""

new_selection = """        def _ah_source_norm(value: str | None) -> str:
            normalized = str(value or '').lower()
            normalized = normalized.replace('€', ' eur ')
            normalized = re.sub(r'[^a-z0-9,\\.]+', ' ', normalized)
            return re.sub(r'\\s+', ' ', normalized).strip()

        def _ah_source_non_product(line: str | None) -> bool:
            norm = _ah_source_norm(line)
            if not norm:
                return True
            non_product_tokens = (
                'subtotaal', 'totaal', 'te betalen', 'betalen', 'betaald met',
                'pinnen', 'pin ', 'v pay', 'v pay', 'vpay',
                'je voordeel', 'jouw voordeel', 'voordeel', 'app deals',
                'bonus', 'bonus box', 'korting',
                'btw', 'eur btw', 'over eur',
                'terminal', 'merchant', 'transactie', 'kaart', 'kaartserienummer',
                'autorisatiecode', 'leesmethode', 'chip', 'nfc', 'contactless',
                'download nu', 'spaar automatisch', 'gratis een product',
                'telefoon', 'station', 'klantticket', 'poi'
            )
            return any(token in norm for token in non_product_tokens)

        def _ah_source_product_label(line: str | None) -> str | None:
            raw = str(line or '').strip()
            if not raw or _ah_source_non_product(raw):
                return None
            if not re.search(r'\\d{1,5}[\\.,]\\d{2}', raw):
                return None
            label = re.sub(r'\\d{1,5}[\\.,]\\d{2}.*$', '', raw).strip()
            label = re.sub(r'^[^A-Za-z0-9]+', '', label).strip()
            label = re.sub(r'^\\d+\\s+', '', label).strip()
            label = re.sub(r'\\s+', ' ', label).strip(' .:-')
            if not re.search(r'[A-Za-z]', label):
                return None
            return label.lower()

        def _ah_looks_like_context(lines: list[str]) -> bool:
            haystack = ' '.join(str(line or '') for line in lines[:20]).lower()
            return (
                'albert heijn' in haystack
                or 'ah to go' in haystack
                or 'app deals' in haystack
                or 'je voordeel' in haystack
                or 'jouw voordeel' in haystack
            )

        def _ah_has_paddle_merged_product_line(paddle_source_lines: list[str], tess_source_lines: list[str]) -> bool:
            tess_labels = []
            for source_line in tess_source_lines or []:
                label = _ah_source_product_label(source_line)
                if label:
                    label_norm = re.sub(r'[^a-z0-9]+', ' ', label).strip()
                    if label_norm and label_norm not in tess_labels:
                        tess_labels.append(label_norm)
            if len(tess_labels) < 2:
                return False
            for paddle_line in paddle_source_lines or []:
                paddle_norm = _ah_source_norm(paddle_line)
                if not paddle_norm or _ah_source_non_product(paddle_line):
                    continue
                hits = 0
                for label in tess_labels:
                    if label and label in paddle_norm:
                        hits += 1
                if hits >= 2:
                    return True
            return False

        def _ah_cleanup_final_lines(lines: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            cleaned = []
            removed = []
            for line in lines or []:
                if not isinstance(line, dict):
                    cleaned.append(line)
                    continue
                label = str(
                    line.get('display_label')
                    or line.get('corrected_raw_label')
                    or line.get('raw_label')
                    or line.get('normalized_label')
                    or ''
                )
                if _ah_source_non_product(label):
                    removed.append({
                        'label': label,
                        'reason': 'ah_final_non_product_filter'
                    })
                    continue
                item = dict(line)
                for key in ('raw_label', 'normalized_label', 'display_label', 'corrected_raw_label'):
                    value = item.get(key)
                    if isinstance(value, str):
                        cleaned_value = re.sub(r'^[^A-Za-z0-9]+', '', value).strip()
                        item[key] = cleaned_value
                cleaned.append(item)
            return cleaned, removed

        ah_ocr_context = _ah_looks_like_context(paddle_lines or tesseract_lines)
        ah_successful_r9_33f = bool(
            safe_rotation_decision
            and getattr(safe_rotation_decision, 'selected_route', None) == 'R9-33F_rembg_dark_region_perspective_normalized'
        )
        ah_paddle_merged_product_line = bool(
            ah_ocr_context
            and ah_successful_r9_33f
            and _ah_has_paddle_merged_product_line(paddle_lines, tesseract_lines)
        )

        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        if ah_paddle_merged_product_line and tesseract_result.is_receipt:
            image_result = tesseract_result

        ah_force_preprocessed_tesseract = bool(image_result is tesseract_result and ah_paddle_merged_product_line)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
        chosen_lines = paddle_lines if image_result is paddle_result else tesseract_lines
"""

old_original_compare = """            best_result = _choose_better_receipt_result(image_result, original_result)
            if best_result is not image_result:
"""

new_original_compare = """            best_result = _choose_better_receipt_result(image_result, original_result)
            if ah_force_preprocessed_tesseract:
                best_result = image_result
            if best_result is not image_result:
"""

old_return_block = """        if image_result.is_receipt:
            if not image_result.lines:
                sparse_lines = _extract_sparse_receipt_lines(chosen_lines or paddle_lines or tesseract_lines, filename, image_result.store_name)
                if sparse_lines:
                    image_result.lines = sparse_lines
                    if image_result.parse_status == 'review_needed':
                        image_result.confidence_score = max(float(image_result.confidence_score or 0.0), 0.38)
            if chosen_confidence is not None and image_result.confidence_score is not None:
                image_result.confidence_score = round(min(image_result.confidence_score, chosen_confidence), 4)
            elif chosen_confidence is not None:
                image_result.confidence_score = round(chosen_confidence, 4)
            return image_result
"""

new_return_block = """        if image_result.is_receipt:
            if not image_result.lines:
                sparse_lines = _extract_sparse_receipt_lines(chosen_lines or paddle_lines or tesseract_lines, filename, image_result.store_name)
                if sparse_lines:
                    image_result.lines = sparse_lines
                    if image_result.parse_status == 'review_needed':
                        image_result.confidence_score = max(float(image_result.confidence_score or 0.0), 0.38)
            ah_removed_final_lines: list[dict[str, Any]] = []
            if ah_ocr_context:
                image_result.lines, ah_removed_final_lines = _ah_cleanup_final_lines(image_result.lines)
            if chosen_confidence is not None and image_result.confidence_score is not None:
                image_result.confidence_score = round(min(image_result.confidence_score, chosen_confidence), 4)
            elif chosen_confidence is not None:
                image_result.confidence_score = round(chosen_confidence, 4)
            diagnostics = dict(image_result.parser_diagnostics or summarize_lines_parser_diagnostics(image_result.lines or []))
            if ah_ocr_context:
                diagnostics['ah_ocr_arbitrage'] = {
                    'branch': 'R9-34J_ah_ocr_engine_arbitrage',
                    'status_neutral': True,
                    'status_classification_changed': False,
                    'po_norm_status_label_touched': False,
                    'preprocessing_route': getattr(safe_rotation_decision, 'selected_route', None) if safe_rotation_decision else None,
                    'paddle_merged_product_line_detected': ah_paddle_merged_product_line,
                    'forced_preprocessed_tesseract': ah_force_preprocessed_tesseract,
                    'chosen_engine': 'tesseract' if image_result is tesseract_result else 'paddle_or_original',
                    'removed_final_lines': ah_removed_final_lines,
                }
                image_result.parser_diagnostics = diagnostics
            return image_result
"""

for label, old, new in [
    ("selection block", old_selection, new_selection),
    ("original comparison block", old_original_compare, new_original_compare),
    ("return block", old_return_block, new_return_block),
]:
    if old not in text:
        raise SystemExit(f"Patch failed: block not found: {label}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("R9-34J patch applied to backend/app/services/receipt_service.py")
