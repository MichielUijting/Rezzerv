from pathlib import Path

root = Path(r"C:\Users\Gebruiker\Rezzerv_Github")

pre_path = root / "backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py"
svc_path = root / "backend/app/services/receipt_service.py"

pre_text = pre_path.read_text(encoding="utf-8")
svc_text = svc_path.read_text(encoding="utf-8")

if "import os\n" not in pre_text:
    pre_text = pre_text.replace("from dataclasses import asdict, dataclass\n", "from dataclasses import asdict, dataclass\nimport os\n")

old_dataclass = """@dataclass
class ReceiptImagePreprocessingDecision:
    preprocessing_step: str
    selected_route: str
    applied_steps: list[str]
    fallback_reason: list[str]
    perspective_normalization: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
"""

new_dataclass = """@dataclass
class ReceiptImagePreprocessingDecision:
    preprocessing_step: str
    selected_route: str
    applied_steps: list[str]
    fallback_reason: list[str]
    perspective_normalization: dict[str, Any] | None
    diagnostics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
"""

if old_dataclass not in pre_text and new_dataclass not in pre_text:
    raise SystemExit("Dataclass-patchpunt niet gevonden in receipt_image_preprocessing.py")
if old_dataclass in pre_text:
    pre_text = pre_text.replace(old_dataclass, new_dataclass)

apply_marker = "def apply_receipt_image_preprocessing(file_bytes: bytes, filename: str) -> tuple[bytes, ReceiptImagePreprocessingDecision]:\n"
if apply_marker not in pre_text:
    raise SystemExit("apply_receipt_image_preprocessing niet gevonden")

prefix = pre_text.split(apply_marker)[0]

new_helpers_and_apply = """def _rembg_mode() -> str:
    value = str(os.getenv("REZZERV_RECEIPT_REMBG_MODE", "shadow") or "shadow").strip().lower()
    if value not in {"off", "shadow", "selective", "force"}:
        return "shadow"
    return value


def _image_difference_ratio(left, right) -> float | None:
    if cv2 is None or np is None or left is None or right is None:
        return None
    try:
        left_small = cv2.resize(left, (256, 256))
        right_small = cv2.resize(right, (256, 256))
        diff = cv2.absdiff(left_small, right_small)
        return round(float(np.mean(diff)) / 255.0, 6)
    except Exception:
        return None


def _debug_dir() -> Path | None:
    value = str(os.getenv("REZZERV_RECEIPT_PREPROCESS_DEBUG_DIR", "") or "").strip()
    if not value:
        return None
    try:
        path = Path(value)
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return None


def _write_debug_image(debug_dir: Path | None, name: str, image) -> None:
    if debug_dir is None or image is None or cv2 is None:
        return
    try:
        cv2.imwrite(str(debug_dir / name), image)
    except Exception:
        return


def _decision(
    *,
    selected_route: str,
    applied_steps: list[str],
    fallback_reason: list[str],
    diagnostics: dict[str, Any] | None = None,
) -> ReceiptImagePreprocessingDecision:
    return ReceiptImagePreprocessingDecision(
        "receipt_image_preprocessing",
        selected_route,
        applied_steps,
        fallback_reason,
        None,
        diagnostics or {},
    )


def apply_receipt_image_preprocessing(file_bytes: bytes, filename: str) -> tuple[bytes, ReceiptImagePreprocessingDecision]:
    # R9-29A: safe Kassa preprocessing with explicit rembg modes.
    #
    # REZZERV_RECEIPT_REMBG_MODE:
    # - off:       never attempt rembg.
    # - shadow:    run rembg diagnostics but keep original/OpenCV route for OCR.
    # - selective: use rembg only when conservative image-level gates pass.
    # - force:     use rembg when available, for local/manual experiments only.
    #
    # Diagnostics explain the choice but never determine parser or PO status.

    suffix = Path(filename or "").suffix.lower()
    mode = _rembg_mode()
    debug_dir = _debug_dir()

    diagnostics: dict[str, Any] = {
        "r9_step": "R9-29A",
        "rembg_mode": mode,
        "filename": filename,
        "suffix": suffix,
        "rembg_available": rembg_remove is not None,
        "pillow_available": Image is not None,
        "cv2_available": cv2 is not None,
        "numpy_available": np is not None,
    }

    if suffix and suffix not in IMAGE_SUFFIXES:
        return file_bytes, _decision(
            selected_route="original",
            applied_steps=[],
            fallback_reason=["unsupported_image_suffix"],
            diagnostics=diagnostics,
        )

    applied_steps: list[str] = []
    fallback_reason: list[str] = []

    original_image = _decode_image(file_bytes)
    if original_image is None:
        return file_bytes, _decision(
            selected_route="original",
            applied_steps=[],
            fallback_reason=["image_decode_failed_or_cv2_unavailable"],
            diagnostics=diagnostics,
        )

    _write_debug_image(debug_dir, "01_original.png", original_image)

    selected_image = original_image
    rembg_image = None
    rembg_reason = None
    rembg_selected = False

    if mode == "off":
        fallback_reason.append("rembg_mode_off")
        diagnostics["rembg_attempted"] = False
    else:
        rembg_image, rembg_reason = _remove_background_with_rembg(file_bytes)
        diagnostics["rembg_attempted"] = True
        diagnostics["rembg_reason"] = rembg_reason

        if rembg_image is None:
            if rembg_reason:
                fallback_reason.append(rembg_reason)
        else:
            _write_debug_image(debug_dir, "10_rembg_candidate.png", rembg_image)
            diff_ratio = _image_difference_ratio(original_image, rembg_image)
            diagnostics["rembg_difference_ratio_vs_original"] = diff_ratio
            diagnostics["rembg_candidate_size"] = list(rembg_image.shape[:2]) if hasattr(rembg_image, "shape") else None

            if mode == "shadow":
                fallback_reason.append("rembg_shadow_mode")
            elif mode == "force":
                selected_image = rembg_image
                rembg_selected = True
                applied_steps.append("ai_background_removed")
            elif mode == "selective":
                if diff_ratio is None:
                    fallback_reason.append("rembg_difference_unavailable")
                elif diff_ratio < 0.01:
                    fallback_reason.append("rembg_output_nearly_identical_to_original")
                else:
                    selected_image = rembg_image
                    rembg_selected = True
                    applied_steps.append("ai_background_removed")

    diagnostics["rembg_selected_for_ocr"] = rembg_selected

    image, document_extracted = _remove_background_by_document_edges(selected_image)
    if document_extracted:
        applied_steps.append("document_edge_background_removed")

    _write_debug_image(debug_dir, "40_final_runtime_preprocessed.png", image)

    output = _encode_image_png(image)
    if not output:
        return file_bytes, _decision(
            selected_route="original",
            applied_steps=applied_steps,
            fallback_reason=fallback_reason + ["output_encode_failed"],
            diagnostics=diagnostics,
        )

    route = "original" if not applied_steps else "+".join(applied_steps)
    diagnostics["final_selected_route"] = route
    diagnostics["final_output_bytes"] = len(output)
    diagnostics["input_bytes"] = len(file_bytes)

    return output, _decision(
        selected_route=route,
        applied_steps=applied_steps,
        fallback_reason=fallback_reason,
        diagnostics=diagnostics,
    )
"""

pre_text = prefix + new_helpers_and_apply
pre_path.write_text(pre_text, encoding="utf-8")

helper_marker = "def _looks_like_non_receipt(lines: list[str]) -> bool:\n"
helper_code = """def _attach_preprocessing_diagnostics(
    result: ReceiptParseResult,
    preprocessing_decision: Any | None,
) -> ReceiptParseResult:
    # R9-29A: read-only Kassa preprocessing diagnostics.
    # This explains the chosen image route but never changes parse_status,
    # PO status, store detection or line extraction.
    if result is None or preprocessing_decision is None:
        return result
    try:
        decision_payload = preprocessing_decision.to_dict() if hasattr(preprocessing_decision, "to_dict") else dict(preprocessing_decision)
    except Exception:
        decision_payload = {"repr": repr(preprocessing_decision)}

    current = result.parser_diagnostics
    if not isinstance(current, dict):
        current = {"parser_diagnostics": current}
    current = dict(current)
    current["preprocessing_decision"] = decision_payload
    current["preprocessing_guardrail"] = {
        "r9_step": "R9-29A",
        "status_determination": "not_performed",
        "status_service": "receipt_status_baseline_service_v4.py",
        "diagnostics_promoted_to_parser": False,
    }
    result.parser_diagnostics = current
    return result


"""

if helper_code.strip() not in svc_text:
    if helper_marker not in svc_text:
        raise SystemExit("Helper-invoegpunt niet gevonden in receipt_service.py")
    svc_text = svc_text.replace(helper_marker, helper_code + helper_marker)

old_return = "            return image_result\n\n        fallback_lines = chosen_lines or paddle_lines or tesseract_lines\n"
new_return = "            return _attach_preprocessing_diagnostics(image_result, safe_rotation_decision)\n\n        fallback_lines = chosen_lines or paddle_lines or tesseract_lines\n"
if old_return not in svc_text and new_return not in svc_text:
    raise SystemExit("image_result return-patchpunt niet gevonden in receipt_service.py")
if old_return in svc_text:
    svc_text = svc_text.replace(old_return, new_return)

old_candidate = """        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
"""
new_candidate = """        _attach_preprocessing_diagnostics(paddle_result, safe_rotation_decision)
        _attach_preprocessing_diagnostics(tesseract_result, safe_rotation_decision)

        image_result = _choose_better_receipt_result(paddle_result, tesseract_result)
        chosen_confidence = paddle_confidence if image_result is paddle_result else tesseract_confidence
"""
if old_candidate not in svc_text and new_candidate not in svc_text:
    raise SystemExit("candidate diagnostics patchpunt niet gevonden in receipt_service.py")
if old_candidate in svc_text:
    svc_text = svc_text.replace(old_candidate, new_candidate)

svc_text = svc_text.replace(
    "LOGGER.warning('Safe rotation preprocessing mislukt voor %s: %s', filename, exc)",
    "LOGGER.warning('Receipt image preprocessing mislukt voor %s: %s', filename, exc)",
)

svc_path.write_text(svc_text, encoding="utf-8")

print("R9-29A toegepast: rembg veilig geïntegreerd in Kassa-preprocessing.")
print("Default mode: REZZERV_RECEIPT_REMBG_MODE=shadow")
print("Modes: off | shadow | selective | force")
print("Geen parserstatus-, PO-status-, database- of UI-statuswijziging.")
print("Aangepast:")
print("- backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py")
print("- backend/app/services/receipt_service.py")
