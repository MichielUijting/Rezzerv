"""Runtime receipt patches.

Release focus:
- keep Kassa/database behaviour unchanged;
- improve article-line count recognition during receipt ingestion;
- do not use baseline as production truth;
- do not approve receipts by tolerance.

This module is loaded by Python at backend startup and patches the legacy
receipt service narrowly until parsing is moved into smaller domain services.
"""

from __future__ import annotations

from decimal import Decimal
import builtins
import functools
import re
import sys
from typing import Any


# Accept normal Dutch prices, negative prices and OCR price-only fragments such
# as ',95'. This is intentionally about line recognition, not status approval.
MONEY_RE = re.compile(r"(?<!\d)-?(?:\d{1,5}[\.,]\d{2}|[\.,]\d{2})(?!\d)")

# Only skip lines that are clearly not article rows. This list is deliberately
# conservative: discounts, stamps, deposits and other financial rows must remain
# visible as receipt lines because the PO uses them in baseline V4.
SKIP_LINE_TOKENS = (
    "totaal", "te betalen", "subtotaal", "subtotal", "btw", "waarvan",
    "bankpas", "pin", "pinnen", "betaling", "betaald", "wisselgeld",
    "kassa", "bonnr", "transactie", "datum", "tijd", "filiaal", "adres",
)

COUNTABLE_FINANCIAL_TOKENS = (
    "koopzegel", "koopzegels", "spaarzegel", "spaarzegels", "pluspunten",
    "plus punten", "statiegeld", "emballage", "korting", "bonus",
    "prijsvoordeel", "actiebon", "actie bon", "coupon", "lidl plus",
    "uw voordeel", "gratis",
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
    if any(t in text for t in ("koopzegel", "koopzegels", "spaarzegel", "spaarzegels", "pluspunten", "plus punten", "statiegeld", "emballage")):
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
    if any(token in text for token in COUNTABLE_FINANCIAL_TOKENS):
        return False
    if any(token in text for token in SKIP_LINE_TOKENS):
        return True
    if re.fullmatch(r"[0-9\s.,:+\-]+", text):
        return True
    return False


def _clean_label_before_price(line: str, match: re.Match[str]) -> str:
    label = line[:match.start()].strip(" -:;€")
    label = re.sub(r"\b\d+\s*[xX]\b", "", label).strip(" -:;€")
    # Remove common quantity/unit price fragments while keeping the product name.
    label = re.sub(r"\b\d+[\.,]?\d*\s*(?:kg|g|l|ml|st)\b", "", label, flags=re.IGNORECASE).strip(" -:;€")
    return label


def _candidate_lines_from_text(text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    previous_label = ""
    raw_lines = [re.sub(r"\s+", " ", line).strip() for line in re.split(r"\r?\n+", text or "")]
    raw_lines = [line for line in raw_lines if line]

    for line in raw_lines:
        matches = list(MONEY_RE.finditer(line))
        if not matches:
            # Keep a possible article label for OCR patterns where the price is
            # printed on the next line, e.g. photo receipts.
            if not _should_skip_candidate(line):
                previous_label = line
            continue

        # Use the last amount on a line as the line total. Earlier amounts on the
        # same line are usually quantity/unit-price fragments.
        match = matches[-1]
        amount = _dec(match.group(0))
        if amount is None:
            previous_label = ""
            continue

        label = _clean_label_before_price(line, match)
        if not label and previous_label:
            label = previous_label
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
            "source": "receipt_article_count_repair",
        })
        previous_label = ""
    return candidates


def _same_line_identity(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_label = _norm(a.get("normalized_label") or a.get("raw_label"))
    b_label = _norm(b.get("normalized_label") or b.get("raw_label"))
    if not a_label or not b_label:
        return False
    return a_label == b_label and _dec(a.get("line_total")) == _dec(b.get("line_total"))


def _merge_missing_lines(existing: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append only truly missing lines.

    Earlier versions used fuzzy similarity to avoid duplicates. That was too
    aggressive for the PO's current test: first make the article count equal to
    baseline V4. Therefore we now only suppress exact same label+amount lines.
    Similar labels with different prices are kept, because they may be separate
    receipt rows.
    """
    merged = list(existing or [])
    for candidate in candidates:
        label = candidate.get("normalized_label") or candidate.get("raw_label")
        amount = _dec(candidate.get("line_total"))
        if not label or amount is None:
            continue
        if any(_same_line_identity(line, candidate) for line in merged):
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
    if getattr(rs, "_rezzerv_article_count_patch_installed", False):
        return

    old_non_product = getattr(rs, "_looks_like_non_product_receipt_label", lambda label: False)

    def looks_like_non_product(label):
        text = _norm(label)
        if any(token in text for token in COUNTABLE_FINANCIAL_TOKENS):
            return False
        return old_non_product(label)

    rs._looks_like_non_product_receipt_label = looks_like_non_product
    rs._line_type_for_label = _line_type

    for name, fn in list(vars(rs).items()):
        if not callable(fn) or getattr(fn, "_rezzerv_article_count_wrapped", False):
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

        wrapper._rezzerv_article_count_wrapped = True
        try:
            setattr(rs, name, wrapper)
        except Exception:
            pass

    rs._rezzerv_article_count_patch_installed = True


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
