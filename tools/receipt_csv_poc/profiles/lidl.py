from .base import ReceiptProfile, PROTECTED_LINE_TYPES


class LidlProfile(ReceiptProfile):
    profile_name = "lidl"

    product_block_start_keywords = [
        "omschrijving",
        "artikelen",
        "producten",
    ]

    product_block_end_keywords = ReceiptProfile.product_block_end_keywords + [
        "uw voordeel",
        "te betalen",
        "betaling pin",
    ]

    def refine_classified_lines(self, classified_lines: list):
        diagnostics = {
            "profile": self.profile_name,
            "refined_lines_count": 0,
            "refinement_reasons": {},
            "refined_line_numbers": [],
        }
        refined = []
        for index, line in enumerate(classified_lines):
            if line.line_type in PROTECTED_LINE_TYPES:
                refined.append(line)
                continue
            normalized = line.normalized_line
            lowered = normalized.lower()
            has_text = any(ch.isalpha() for ch in normalized)
            has_lidl_vat_suffix = lowered.endswith(" b") or lowered.endswith(" a")
            next_line = classified_lines[index + 1] if index + 1 < len(classified_lines) else None
            next_is_quantity = bool(next_line and next_line.line_type == "quantity_line")
            if line.line_type == "unknown_line" and has_text and (has_lidl_vat_suffix or next_is_quantity):
                reason = "lidl_unknown_with_vat_suffix_or_next_quantity"
                refined_line = self._replace_classification(line, "product_line", reason)
                self._record_refinement(diagnostics, line.line_no, reason)
                refined.append(refined_line)
                continue
            refined.append(line)
        return refined, diagnostics
