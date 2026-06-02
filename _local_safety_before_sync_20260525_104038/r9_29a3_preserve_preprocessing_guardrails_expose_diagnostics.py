from pathlib import Path

root = Path(r"C:\Users\Gebruiker\Rezzerv_Github")
svc_path = root / "backend/app/services/receipt_service.py"

text = svc_path.read_text(encoding="utf-8")

helper = '''def _attach_preprocessing_diagnostics(
    result: ReceiptParseResult,
    preprocessing_decision: Any | None,
) -> ReceiptParseResult:
    # R9-29A3: attach read-only preprocessing diagnostics to the parse result.
    #
    # Guardrails:
    # - Preserve existing R9-27C rembg/PCA route-gates.
    # - Do not broaden rembg/PCA usage.
    # - Do not change parse_status, store detection, line extraction or PO status.
    # - Do not mutate receipt_status_baseline_service_v4.py.
    if result is None or preprocessing_decision is None:
        return result

    try:
        decision_payload = (
            preprocessing_decision.to_dict()
            if hasattr(preprocessing_decision, "to_dict")
            else dict(preprocessing_decision)
        )
    except Exception:
        decision_payload = {"repr": repr(preprocessing_decision)}

    current = result.parser_diagnostics
    if not isinstance(current, dict):
        current = {"parser_diagnostics": current}
    else:
        current = dict(current)

    current["preprocessing_decision"] = decision_payload
    current["preprocessing_guardrail"] = {
        "r9_step": "R9-29A3",
        "status_determination": "not_performed",
        "status_service": "receipt_status_baseline_service_v4.py",
        "diagnostics_promoted_to_parser": False,
        "preprocessing_functional_change": False,
        "pca_pilot_gate_broadened": False,
        "rembg_default_route_changed": False,
    }

    result.parser_diagnostics = current
    return result


'''

if "def _attach_preprocessing_diagnostics(" not in text:
    marker = "def _looks_like_non_receipt(lines: list[str]) -> bool:"
    if marker not in text:
        raise SystemExit("Invoegpunt niet gevonden: def _looks_like_non_receipt")
    text = text.replace(marker, helper + marker, 1)

old_candidate = '''        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
        chosen_lines = paddle_lines if image_result is paddle_result else tesseract_lines
'''

new_candidate = '''        _attach_preprocessing_diagnostics(paddle_result, safe_rotation_decision)
        _attach_preprocessing_diagnostics(tesseract_result, safe_rotation_decision)

        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
        chosen_lines = paddle_lines if image_result is paddle_result else tesseract_lines
'''

if old_candidate in text:
    text = text.replace(old_candidate, new_candidate, 1)
elif new_candidate not in text:
    raise SystemExit("Patchpunt niet gevonden rond _choose_better_receipt_result")

old_success_return = '''            return image_result

        fallback_lines = chosen_lines or paddle_lines or tesseract_lines
'''

new_success_return = '''            return _attach_preprocessing_diagnostics(image_result, safe_rotation_decision)

        fallback_lines = chosen_lines or paddle_lines or tesseract_lines
'''

if old_success_return in text:
    text = text.replace(old_success_return, new_success_return, 1)
elif new_success_return not in text:
    raise SystemExit("Patchpunt niet gevonden rond return image_result")

old_fallback_return = '''        return ReceiptParseResult(
            is_receipt=True,
            parse_status='review_needed',
            confidence_score=confidence,
            store_name=store_name,
            purchase_at=purchase_at,
            total_amount=total_amount,
            discount_total=None,
            currency='EUR',
            lines=[],
            parser_diagnostics=summarize_lines_parser_diagnostics([]),
        )
'''

new_fallback_return = '''        fallback_result = ReceiptParseResult(
            is_receipt=True,
            parse_status='review_needed',
            confidence_score=confidence,
            store_name=store_name,
            purchase_at=purchase_at,
            total_amount=total_amount,
            discount_total=None,
            currency='EUR',
            lines=[],
            parser_diagnostics=summarize_lines_parser_diagnostics([]),
        )
        return _attach_preprocessing_diagnostics(fallback_result, safe_rotation_decision)
'''

if old_fallback_return in text:
    text = text.replace(old_fallback_return, new_fallback_return, 1)
elif new_fallback_return not in text:
    raise SystemExit("Patchpunt niet gevonden rond image fallback ReceiptParseResult")

text = text.replace(
    "LOGGER.warning('Safe rotation preprocessing mislukt voor %s: %s', filename, exc)",
    "LOGGER.warning('Receipt image preprocessing mislukt voor %s: %s', filename, exc)",
)

svc_path.write_text(text, encoding="utf-8")

print("R9-29A3 toegepast.")
print("Alleen receipt_service.py aangepast.")
print("receipt_image_preprocessing.py is functioneel ongemoeid gelaten.")
print("Bestaande R9-27C rembg/PCA route-gates blijven intact.")
print("Preprocessing decision wordt read-only toegevoegd aan parser_diagnostics.")
print("Geen parserstatus-, PO-status-, database-, OCR-engine- of UI-statuswijziging.")
