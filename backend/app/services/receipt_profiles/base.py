from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class ReceiptProfileContext:
    store_name: str | None
    filename: str | None = None
    raw_lines: list[str] | None = None


class ReceiptProfile(Protocol):
    profile_id: str
    store_aliases: tuple[str, ...]

    def normalize_lines(self, lines: list[dict[str, Any]], context: ReceiptProfileContext) -> list[dict[str, Any]]: ...

    def normalize_totals(
        self,
        *,
        total_amount: Decimal | None,
        discount_total: Decimal | None,
        lines: list[dict[str, Any]],
        context: ReceiptProfileContext,
    ) -> tuple[Decimal | None, Decimal | None]: ...


class BaseReceiptProfile:
    profile_id = "generic"
    store_aliases: tuple[str, ...] = ()

    def normalize_lines(self, lines, context):
        return list(lines or [])

    def normalize_totals(self, *, total_amount, discount_total, lines, context):
        return total_amount, discount_total
