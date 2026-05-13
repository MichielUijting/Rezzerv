from __future__ import annotations

from dataclasses import dataclass, replace

PARSEABLE_LINE_TYPES = {"product_line", "quantity_line"}


@dataclass
class ProductBlock:
    start_line: int | None
    end_line: int | None
    reason: str
    line_count: int


class ReceiptProfile:
    profile_name = "generic"
    merge_strategy = "previous_product"

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

    def _find_previous_product_index(self, rows: list, quantity_index: int) -> int | None:
        for candidate_index in range(quantity_index - 1, -1, -1):
            if rows[candidate_index].line_type == "product_line":
                return candidate_index
        return None

    def _find_next_product_index(self, rows: list, quantity_index: int) -> int | None:
        for candidate_index in range(quantity_index + 1, len(rows)):
            if rows[candidate_index].line_type == "product_line":
                return candidate_index
        return None

    def _target_product_index(self, rows: list, quantity_index: int) -> int | None:
        return self._find_previous_product_index(rows, quantity_index)

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

    def merge_quantity_lines(self, rows: list, classified_lines) -> tuple[list, dict[str, object]]:
        merged_rows = list(rows)
        remove_indexes: set[int] = set()
        merged_count = 0
        unmerged_count = 0

        for index, row in enumerate(merged_rows):
            if row.line_type != "quantity_line":
                continue
            target_index = self._target_product_index(merged_rows, index)
            if target_index is None:
                unmerged_count += 1
                continue
            merged_rows[target_index] = self._merge_quantity_into_product(merged_rows[target_index], row)
            remove_indexes.add(index)
            merged_count += 1

        output_rows = [row for index, row in enumerate(merged_rows) if index not in remove_indexes]
        diagnostics = {
            "merge_strategy": self.merge_strategy,
            "merged_quantity_lines_count": merged_count,
            "unmerged_quantity_lines_count": unmerged_count,
            "input_rows_count": len(rows),
            "output_rows_count": len(output_rows),
        }
        return output_rows, diagnostics


class GenericProfile(ReceiptProfile):
    profile_name = "generic"
    merge_strategy = "previous_product"
