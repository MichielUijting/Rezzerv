from .base import ReceiptProfile, PROTECTED_LINE_TYPES


class JumboProfile(ReceiptProfile):
    profile_name = "jumbo"
    merge_strategy = "safe_previous_product_jumbo"
    max_quantity_merge_distance = 2

    product_block_start_keywords = [
        "omschrijving",
        "producten",
        "aantal omschrijving",
    ]

    product_block_end_keywords = ReceiptProfile.product_block_end_keywords + [
        "te betalen",
        "uw korting",
        "pinbetaling",
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
            next_line = classified_lines[index + 1] if index + 1 < len(classified_lines) else None
            next_is_quantity = bool(next_line and next_line.line_type == "quantity_line")
            looks_like_jumbo_product = has_text and (
                lowered.startswith("jumbo ")
                or next_is_quantity
                or any(token in lowered for token in ["komkommer", "broccoli", "chorizo", "melk", "rijst"])
            )
            if line.line_type == "unknown_line" and looks_like_jumbo_product:
                reason = "jumbo_unknown_product_context"
                refined_line = self._replace_classification(line, "product_line", reason)
                self._record_refinement(diagnostics, line.line_no, reason)
                refined.append(refined_line)
                continue
            refined.append(line)
        return refined, diagnostics

    def _target_product_index(self, rows: list, quantity_index: int):
        # Conservative Jumbo rule: only merge with a nearby previous product.
        # Never scan further back across other product rows.
        return self._find_safe_previous_product_index(rows, quantity_index)
