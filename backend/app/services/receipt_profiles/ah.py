from .base import BaseReceiptProfile


class AlbertHeijnReceiptProfile(BaseReceiptProfile):
    profile_id = "ah"
    store_aliases = ("albert heijn", "ah")

    def normalize_lines(self, lines, context):
        fixed = []
        for line in lines or []:
            if not isinstance(line, dict):
                fixed.append(line)
                continue
            label = str(line.get("normalized_label") or line.get("raw_label") or "").lower()
            if "koopzegel" in label or "spaarzegel" in label:
                qty = line.get("quantity")
                try:
                    if qty is not None:
                        line["line_total"] = round(float(qty) * 0.10, 2)
                except Exception:
                    pass
            fixed.append(line)
        return fixed
