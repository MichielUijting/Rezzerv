from __future__ import annotations

from dataclasses import dataclass

PARSEABLE_LINE_TYPES = {"product_line", "quantity_line"}


@dataclass
class ProductBlock:
    start_line: int | None
    end_line: int | None
    reason: str
    line_count: int


class ReceiptProfile:
    profile_name = "generic"

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


class GenericProfile(ReceiptProfile):
    profile_name = "generic"
