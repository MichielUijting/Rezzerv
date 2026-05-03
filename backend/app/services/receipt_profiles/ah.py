import re

from .base import BaseReceiptProfile


class AlbertHeijnReceiptProfile(BaseReceiptProfile):
    profile_id = "ah"
    store_aliases = ("albert heijn", "ah")

    def _parse_amount(self, value):
        raw = str(value or "").replace("€", "").replace("EUR", "").strip()
        raw = raw.replace(".", "").replace(",", ".") if "," in raw else raw
        raw = re.sub(r"[^0-9\-.]", "", raw)
        if not raw:
            return None
        try:
            return round(float(raw), 2)
        except Exception:
            return None

    def _koopzegel_line_from_raw_text(self, raw_lines):
        for index, raw_line in enumerate(raw_lines or []):
            text = str(raw_line or "").strip()
            lowered = text.lower()
            if "koopzegel" not in lowered and "spaarzegel" not in lowered:
                continue
            amounts = re.findall(r"-?\d+(?:[\.,]\d{2})", text)
            if not amounts:
                continue
            amount = self._parse_amount(amounts[-1])
            if amount is None or amount <= 0:
                continue
            label = re.sub(r"^\s*\d+\s+", "", text)
            label = re.sub(r"\s+-?\d+(?:[\.,]\d{2})\s*$", "", label).strip() or "KOOPZEGELS"
            return {
                "raw_label": label,
                "normalized_label": label,
                "quantity": None,
                "unit": None,
                "unit_price": amount,
                "line_total": amount,
                "discount_amount": None,
                "barcode": None,
                "confidence_score": 0.85,
                "source_index": index,
            }
        return None

    def normalize_lines(self, lines, context):
        fixed = []
        has_koopzegel = False
        for line in lines or []:
            if not isinstance(line, dict):
                fixed.append(line)
                continue
            label = str(line.get("normalized_label") or line.get("raw_label") or "").lower()
            if "koopzegel" in label or "spaarzegel" in label:
                has_koopzegel = True
                fixed.append(line)
                continue
            if line.get("quantity") is None and line.get("discount_amount") is not None:
                continue
            fixed.append(line)

        if not has_koopzegel:
            koopzegel_line = self._koopzegel_line_from_raw_text(getattr(context, "raw_lines", None))
            if koopzegel_line:
                fixed.append(koopzegel_line)

        return fixed

    def normalize_totals(self, *, total_amount, discount_total, lines, context):
        if discount_total is None:
            return total_amount, discount_total
        try:
            from decimal import Decimal
            return total_amount, abs(Decimal(str(discount_total)))
        except Exception:
            return total_amount, discount_total
