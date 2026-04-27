"""Runtime receipt patches.

Release focus:
- keep Kassa/database behaviour unchanged;
- improve article-line recognition during receipt ingestion;
- do not use baseline as production truth;
- do not approve receipts by tolerance.

The app still contains a large legacy receipt service. This module is loaded by
Python at backend startup and patches that legacy service in a narrow way until
receipt parsing is fully moved into smaller domain services.
"""

from __future__ import annotations

from decimal import Decimal
import builtins
import functools
import inspect
import re
import sys
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
            # Keep a possible article label for the common OCR pattern where the
            # price is printed on the next line, e.g. AH photo receipts.
            if not _should_skip_candidate(line):
                previous_label = line
            continue

        match = matches[-1]
        amount = _dec(match.group(0))
        if amount is None:
            previous_label = ""
            continue

        label = line[:match.start()].strip(" -:;€")
        # If the line contains only a price such as ',95', combine it with the
        # preceding label line. This specifically fixes photo receipts where OCR
        # splits article and price over two lines.
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
            # Do not add a second copy of the same label with a different price;
            # price-correction is a separate next step requested by the PO.
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

    # Keep stamp/points lines in the parser output instead of filtering them as
    # non-products. This is article-line recognition, not approval logic.
    old_non_product = getattr(rs, "_looks_like_non_product_receipt_label", lambda label: False)

    def looks_like_non_product(label):
        text = _norm(label)
        if any(token in text for token in FINANCIAL_PRODUCT_TOKENS):
            return False
        return old_non_product(label)

    rs._looks_like_non_product_receipt_label = looks_like_non_product
    rs._line_type_for_label = _line_type

    # Wrap parser-like functions generically. We only modify return values that
    # look like ReceiptParseResult, so normal helper functions are left alone.
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


_original_import = builtins.__import__


def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if name.startswith("app.services.receipt_service") or name == "app.main" or (name == "app" and "main" in (fromlist or ())):
        _try_patch_main()
    return module


builtins.__import__ = _import_hook
_install_receipt_service_patch()
_try_patch_main()
