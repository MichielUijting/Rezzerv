from __future__ import annotations

from dataclasses import dataclass, replace

PARSEABLE_LINE_TYPES = {"product_line", "quantity_line"}
PROTECTED_LINE_TYPES = {"metadata_line", "payment_line", "vat_line", "total_line", "discount_line", "noise_line"}


@dataclass
class ProductBlock:
    start_line: int | None
    end_line: int | None
    reason: str
    line_count: int


class ReceiptProfile:
    profile_name = "generic"
    merge_strategy = "safe_previous_product"
    max_quantity_merge_distance = 1

    product_block_start_keywords = [
        "omschrijving",
        "prijs bedrag",
        "aantal omschrijving",
        "producten",
    ]

    product_block_end_keywords = [
        "aantal art",
        "aantal artikelen",
        "subtotaal",
        "sub tota",
        "bedrag euro",
        "bedrag = euro",
        "totaal",
        "bankpas",
        "pin",
        "pinnen",
        "betaling",
        "contant",
        "visa",
        "vpay",
        "v pay",
        "maestro",
        "mastercard",
        "contactless",
        "terminal",
        "merchant",
        "transactie",
        "btw",
        "bedr.excl",
        "bedr.incl",
    ]

    def line_contains_any(self, line: str, keywords: list[str]) -> bool:
        lowered = line.lower()
        return any(keyword in lowered for keyword in keywords)

    def refine_classified_lines(self, classified_lines: list) -> tuple[list, dict[str, object]]:
        return classified_lines, {
            "profile": self.profile_name,
            "refined_lines_count": 0,
            "refinement_reasons": {},
            "refined_line_numbers": [],
        }

    def _replace_classification(self, line, line_type: str, reason: str):
        return replace(line, line_type=line_type, reason=reason)

    def _record_refinement(self, diagnostics: dict[str, object], line_no: int, reason: str) -> None:
        diagnostics["refined_lines_count"] = int(diagnostics.get("refined_lines_count", 0)) + 1
        diagnostics.setdefault("refined_line_numbers", []).append(int(line_no))
        reasons = diagnostics.setdefault("refinement_reasons", {})
        reasons[reason] = reasons.get(reason, 0) + 1

    def detect_product_block(self, classified_lines) -> dict[str, object]:
        non_empty = [line for line in classified_lines if line.normalized_line]
        start_line = None
        end_line = None
        reason = "fallback_first_parseable_line"

        for line in non_empty:
            if self.line_contains_any(line.normalized_line, self.product_block_start_keywords):
                start_line = line.line_no + 1
                reason = "header_keyword"
                break

        if start_line is None:
            for line in non_empty:
                if line.line_type in PARSEABLE_LINE_TYPES:
                    start_line = line.line_no
                    break

        if start_line is None:
            return {
                "start_line": None,
                "end_line": None,
                "reason": "no_parseable_lines",
                "line_count": 0,
                "profile": self.profile_name,
            }

        parseable_seen = 0
        for line in non_empty:
            if line.line_no < start_line:
                continue
            if line.line_type in PARSEABLE_LINE_TYPES:
                parseable_seen += 1
            if parseable_seen > 0 and (
                line.line_type in {"total_line", "payment_line", "vat_line"}
                or self.line_contains_any(line.normalized_line, self.product_block_end_keywords)
            ):
                end_line = max(start_line, line.line_no - 1)
                break

        if end_line is None:
            parseable_lines = [
                line.line_no for line in non_empty
                if line.line_no >= start_line and line.line_type in PARSEABLE_LINE_TYPES
            ]
            end_line = max(parseable_lines) if parseable_lines else start_line

        return {
            "start_line": start_line,
            "end_line": end_line,
            "reason": reason,
            "line_count": max(0, end_line - start_line + 1),
            "profile": self.profile_name,
        }

    def _merge_warning(self, existing_warning: str, suffix: str) -> str:
        parts = [part for part in (existing_warning or "").split(";") if part]
        if suffix not in parts:
            parts.append(suffix)
        return ";".join(parts)

    def _find_safe_previous_product_index(self, rows: list, quantity_index: int) -> tuple[int | None, str]:
        quantity_row = rows[quantity_index]
        for candidate_index in range(quantity_index - 1, -1, -1):
            candidate = rows[candidate_index]
            if candidate.line_type == "quantity_line":
                continue
            if candidate.line_type != "product_line":
                return None, "blocked_by_non_product_row"
            distance = int(quantity_row.line_no) - int(candidate.line_no)
            if distance <= self.max_quantity_merge_distance:
                return candidate_index, "safe_previous_product"
            return None, "line_distance_too_large"
        return None, "no_previous_product"

    def _target_product_index(self, rows: list, quantity_index: int) -> tuple[int | None, str]:
        return self._find_safe_previous_product_index(rows, quantity_index)

    def _merge_quantity_into_product(self, product_row, quantity_row):
        quantity = quantity_row.quantity or product_row.quantity
        unit = quantity_row.unit or product_row.unit
        unit_price = quantity_row.unit_price or product_row.unit_price
        line_total = quantity_row.line_total or product_row.line_total
        raw_line = f"{product_row.raw_line} | {quantity_row.raw_line}"
        warning = self._merge_warning(product_row.warning, "quantity_line_merged")
        confidence = min(product_row.parser_confidence, quantity_row.parser_confidence)
        return replace(
            product_row,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            line_total=line_total,
            parser_confidence=confidence,
            raw_line=raw_line,
            warning=warning,
        )

    def _mark_rejected_quantity(self, row, reason: str):
        return replace(row, warning=self._merge_warning(row.warning, f"quantity_merge_rejected:{reason}"))

    def merge_quantity_lines(self, rows: list, classified_lines) -> tuple[list, dict[str, object]]:
        merged_rows = list(rows)
        remove_indexes: set[int] = set()
        merged_pairs: list[dict[str, int]] = []
        rejection_reasons: dict[str, int] = {}
        merge_candidates_count = 0
        rejected_count = 0

        for index, row in enumerate(merged_rows):
            if row.line_type != "quantity_line":
                continue
            merge_candidates_count += 1
            target_index, reason = self._target_product_index(merged_rows, index)
            if target_index is None:
                rejected_count += 1
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                merged_rows[index] = self._mark_rejected_quantity(row, reason)
                continue
            merged_rows[target_index] = self._merge_quantity_into_product(merged_rows[target_index], row)
            remove_indexes.add(index)
            merged_pairs.append({
                "product_line_no": int(merged_rows[target_index].line_no),
                "quantity_line_no": int(row.line_no),
            })

        output_rows = [row for index, row in enumerate(merged_rows) if index not in remove_indexes]
        diagnostics = {
            "merge_strategy": self.merge_strategy,
            "merge_candidates_count": merge_candidates_count,
            "merged_quantity_lines_count": len(merged_pairs),
            "unmerged_quantity_lines_count": rejected_count,
            "rejected_quantity_lines_count": rejected_count,
            "rejection_reasons": rejection_reasons,
            "merged_pairs": merged_pairs,
            "input_rows_count": len(rows),
            "output_rows_count": len(output_rows),
        }
        return output_rows, diagnostics


class GenericProfile(ReceiptProfile):
    profile_name = "generic"
    merge_strategy = "safe_previous_product"
    max_quantity_merge_distance = 1
