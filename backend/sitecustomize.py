"""Runtime receipt patches.

Release focus:
- keep Kassa/database behaviour unchanged;
- improve article-line recognition during receipt ingestion;
- do not use baseline as production truth;
- do not approve receipts by tolerance;
- harden receipt status baseline diagnostics so status mismatches are never counted as correct.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
import builtins
import functools
import re
from typing import Any


MONEY_RE = re.compile(r"(?<!\d)-?(?:\d{1,5}[\.,]\d{2}|[\.,]\d{2})(?!\d)")

SKIP_LINE_TOKENS = (
    "totaal", "te betalen", "subtotaal", "subtotal", "btw", "waarvan",
    "bankpas", "pin", "pinnen", "betaling", "betaald", "wisselgeld",
    "kassa", "bonnr", "transactie", "datum", "tijd", "filiaal", "adres",
)

FINANCIAL_PRODUCT_TOKENS = (
    "koopzegel", "koopzegels", "spaarzegel", "spaarzegels", "pluspunten",
    "plus punten", "statiegeld", "emballage",
)


def _dec(value: Any):
    if value is None:
        return None
    try:
        cleaned = str(value).replace("€", "").replace("EUR", "").strip()
        cleaned = cleaned.replace(".", "").replace(",", ".") if "," in cleaned and "." in cleaned else cleaned.replace(",", ".")
        if cleaned.startswith("."):
            cleaned = "0" + cleaned
        if cleaned.startswith("-."):
            cleaned = "-0" + cleaned[1:]
        cleaned = re.sub(r"[^0-9\-.]", "", cleaned)
        if cleaned in {"", "-", ".", "-."}:
            return None
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except Exception:
        return None


def _norm(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    text = re.sub(r"[^a-z0-9à-ÿ€.,+\- ]+", "", text)
    return text.strip()


def _line_type(label: str | None, amount=None) -> str:
    text = _norm(label)
    amt = _dec(amount)
    if not text:
        return "noise"
    if any(t in text for t in FINANCIAL_PRODUCT_TOKENS):
        return "stamp_or_points"
    if any(t in text for t in ("korting", "bonus", "prijsvoordeel", "actiebon", "actie bon", "coupon", "lidl plus", "uw voordeel", "gratis")):
        return "discount" if amt is None or amt <= 0 else "financial_correction"
    if any(t in text for t in ("bankpas", "betaling", "betaald", "pin", "contant", "wisselgeld")):
        return "payment"
    if any(t in text for t in ("totaal", "subtotaal", "btw", "te betalen")):
        return "total"
    return "product"


def _should_skip_candidate(label: str) -> bool:
    text = _norm(label)
    if not text or len(text) < 2:
        return True
    if any(token in text for token in FINANCIAL_PRODUCT_TOKENS):
        return False
    if any(token in text for token in SKIP_LINE_TOKENS):
        return True
    if re.fullmatch(r"[0-9\s.,:+\-]+", text):
        return True
    return False


def _candidate_lines_from_text(text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    previous_label = ""
    raw_lines = [re.sub(r"\s+", " ", line).strip() for line in re.split(r"\r?\n+", text or "")]
    raw_lines = [line for line in raw_lines if line]

    for line in raw_lines:
        matches = list(MONEY_RE.finditer(line))
        if not matches:
            if not _should_skip_candidate(line):
                previous_label = line
            continue

        match = matches[-1]
        amount = _dec(match.group(0))
        if amount is None:
            previous_label = ""
            continue

        label = line[:match.start()].strip(" -:;€")
        if not label and previous_label:
            label = previous_label
        label = re.sub(r"\b\d+\s*[xX]\b", "", label).strip(" -:;€")
        if _should_skip_candidate(label):
            previous_label = ""
            continue

        kind = _line_type(label, amount)
        if kind in {"payment", "total", "noise"}:
            previous_label = ""
            continue
        candidates.append({
            "raw_label": label[:255],
            "normalized_label": _norm(label)[:255],
            "quantity": 1.0,
            "line_total": float(amount),
            "line_type": kind,
            "source": "receipt_line_repair",
        })
        previous_label = ""
    return candidates


def _similarity(a: Any, b: Any) -> float:
    try:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    except Exception:
        return 0.0


def _merge_missing_lines(existing: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(existing or [])
    for candidate in candidates:
        label = candidate.get("normalized_label") or candidate.get("raw_label")
        amount = _dec(candidate.get("line_total"))
        if not label or amount is None:
            continue
        duplicate = False
        for line in merged:
            current_label = line.get("normalized_label") or line.get("raw_label")
            current_amount = _dec(line.get("line_total"))
            if current_amount == amount and _similarity(current_label, label) >= 0.72:
                duplicate = True
                break
            if _similarity(current_label, label) >= 0.88:
                duplicate = True
                break
        if duplicate:
            continue
        merged.append(candidate)
    return merged


def _extract_text_for_repair(rs, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    text_chunks: list[str] = []
    values = list(args) + list(kwargs.values())
    for value in values:
        if isinstance(value, str) and ("\n" in value or len(value) > 120):
            text_chunks.append(value)
        elif isinstance(value, (bytes, bytearray)):
            data = bytes(value)
            if data.startswith(b"%PDF") and callable(getattr(rs, "_extract_pdf_text", None)):
                try:
                    text_chunks.append(rs._extract_pdf_text(data) or "")
                except Exception:
                    pass
            else:
                for name in ("_extract_image_text", "_extract_text_from_image", "_ocr_image_text", "_paddle_ocr_text"):
                    fn = getattr(rs, name, None)
                    if callable(fn):
                        try:
                            text = fn(data)
                            if text:
                                text_chunks.append(str(text))
                                break
                        except Exception:
                            continue
    return "\n".join(chunk for chunk in text_chunks if chunk)


def _repair_parse_result(rs, result, args: tuple[Any, ...], kwargs: dict[str, Any]):
    if not result or not hasattr(result, "lines"):
        return result
    text = _extract_text_for_repair(rs, args, kwargs)
    if not text:
        return result
    candidates = _candidate_lines_from_text(text)
    if not candidates:
        return result
    existing = getattr(result, "lines", None) or []
    repaired = _merge_missing_lines(existing, candidates)
    if len(repaired) > len(existing):
        result.lines = repaired
    return result


def _install_line_recognition_patch(rs) -> None:
    if getattr(rs, "_rezzerv_line_recognition_patch_installed", False):
        return

    old_non_product = getattr(rs, "_looks_like_non_product_receipt_label", lambda label: False)

    def looks_like_non_product(label):
        text = _norm(label)
        if any(token in text for token in FINANCIAL_PRODUCT_TOKENS):
            return False
        return old_non_product(label)

    rs._looks_like_non_product_receipt_label = looks_like_non_product
    rs._line_type_for_label = _line_type

    for name, fn in list(vars(rs).items()):
        if not callable(fn) or getattr(fn, "_rezzerv_line_repair_wrapped", False):
            continue
        lowered = name.lower()
        if "parse" not in lowered and "receipt" not in lowered:
            continue
        if name.startswith("_") and name not in {"_parse_receipt_from_text", "_parse_receipt_lines", "_parse_lines"}:
            continue

        @functools.wraps(fn)
        def wrapper(*args, __fn=fn, **kwargs):
            result = __fn(*args, **kwargs)
            return _repair_parse_result(rs, result, args, kwargs)

        wrapper._rezzerv_line_repair_wrapped = True
        try:
            setattr(rs, name, wrapper)
        except Exception:
            pass

    rs._rezzerv_line_recognition_patch_installed = True


def _canonical_parse_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"approved", "parsed", "approved_override"}:
        return "approved"
    if normalized in {"review_needed", "partial"}:
        return "review_needed"
    if normalized in {"manual", "failed"}:
        return "manual"
    return normalized


def _status_label(value: Any) -> str:
    canonical = _canonical_parse_status(value)
    if canonical == "approved":
        return "Gecontroleerd"
    if canonical == "review_needed":
        return "Controle nodig"
    if canonical == "manual":
        return "Handmatig"
    return str(value or "") or "-"


def _scope_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _recount_baseline_details(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    details = result.get("details")
    if not isinstance(details, list):
        return result

    scope_rows = result.get("included_receipt_scope") or []
    scope_by_id = {str(row.get("receipt_table_id") or ""): row for row in scope_rows if isinstance(row, dict) and row.get("receipt_table_id")}
    scope_by_file = {
        _scope_key(row.get("source_file") or row.get("original_filename")): row
        for row in scope_rows
        if isinstance(row, dict) and (row.get("source_file") or row.get("original_filename"))
    }

    counts = Counter()
    for item in details:
        if not isinstance(item, dict):
            continue
        receipt_table_id = str(item.get("receipt_table_id") or "")
        actual_row = scope_by_id.get(receipt_table_id)
        if actual_row is None:
            actual_row = scope_by_file.get(_scope_key(item.get("matched_original_filename") or item.get("source_file")))
        if actual_row and actual_row.get("parse_status") is not None:
            real_actual_status = str(actual_row.get("parse_status") or "").strip()
            item["actual_parse_status"] = real_actual_status
            item["actual_status_label"] = _status_label(real_actual_status)
        expected = _canonical_parse_status(item.get("expected_parse_status"))
        actual = _canonical_parse_status(item.get("actual_parse_status"))

        if item.get("result") not in {"missing", "extra"} and expected and actual and expected != actual:
            existing_type = item.get("difference_type")
            if existing_type not in {"mapping_mismatch", "extraction_mismatch"}:
                item["result"] = "different"
                item["reason"] = "Actuele backendstatus wijkt af van de baseline."
                item["difference_type"] = "status_logic_mismatch"
                item["difference_reason"] = "status wijkt af terwijl mapping en extractie voldoende overeenkomen"
                item["status_reason"] = item["difference_reason"]

        result_key = item.get("result")
        if result_key == "correct":
            counts["correct"] += 1
        elif result_key == "missing":
            counts["missing"] += 1
            counts["mapping_mismatch"] += 1
        elif result_key == "extra":
            counts["extra"] += 1
            counts["mapping_mismatch"] += 1
        else:
            counts["different"] += 1
            dtype = item.get("difference_type") or "different"
            counts[dtype] += 1

    summary = dict(result.get("summary") or result.get("validation_summary") or {})
    for key in ("correct", "different", "missing", "extra", "mapping_mismatch", "extraction_mismatch", "status_logic_mismatch"):
        summary[key] = counts[key]
    mismatch_breakdown = Counter()
    for item in details:
        if isinstance(item, dict) and item.get("result") == "different":
            mismatch_breakdown[item.get("difference_type") or "different"] += 1
    summary["mismatch_breakdown"] = dict(sorted(mismatch_breakdown.items()))
    if "summary" in result:
        result["summary"] = summary
    if "validation_summary" in result:
        result["validation_summary"] = summary
    return result


def _install_receipt_status_baseline_patch() -> None:
    try:
        from app.services import receipt_status_baseline_service as svc
    except Exception:
        return
    if getattr(svc, "_rezzerv_strict_status_diagnosis_patch_installed", False):
        return

    old_validate = getattr(svc, "validate_receipt_status_baseline", None)
    if callable(old_validate):
        @functools.wraps(old_validate)
        def validate_wrapper(*args, **kwargs):
            return _recount_baseline_details(old_validate(*args, **kwargs))
        svc.validate_receipt_status_baseline = validate_wrapper

    old_diagnose = getattr(svc, "diagnose_receipt_status_baseline", None)
    if callable(old_diagnose):
        @functools.wraps(old_diagnose)
        def diagnose_wrapper(*args, **kwargs):
            return _recount_baseline_details(old_diagnose(*args, **kwargs))
        svc.diagnose_receipt_status_baseline = diagnose_wrapper

    svc._rezzerv_strict_status_diagnosis_patch_installed = True


def _install_receipt_service_patch() -> None:
    try:
        from app.services import receipt_service as rs
    except Exception:
        return
    _install_line_recognition_patch(rs)


def _try_patch_main() -> None:
    try:
        from app.services import receipt_service as rs
        _install_line_recognition_patch(rs)
    except Exception:
        pass
    _install_receipt_status_baseline_patch()


_original_import = builtins.__import__


def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if (
        name.startswith("app.services.receipt_service")
        or name.startswith("app.services.receipt_status_baseline_service")
        or name == "app.main"
        or (name == "app" and "main" in (fromlist or ()))
    ):
        _try_patch_main()
    return module


builtins.__import__ = _import_hook
_install_receipt_service_patch()
_install_receipt_status_baseline_patch()
_try_patch_main()
