"""Self-contained check for the receipt discount contract.

M2C2i-AH-Photo-03b

Contract decision: Variant B.

``receipt_tables.discount_total`` may be a summary/diagnostic total for
receipt discounts that can also be assigned to individual receipt lines in
``receipt_table_lines.discount_amount``.

Therefore diagnostic checks must not blindly add both values together. A
receipt can be financially valid when either of these interpretations closes:

- line_total_sum + line_discount_sum == expected_total
- line_total_sum + discount_total == expected_total

The motivating example is AH foto 14:

- line_total_sum: 27.61
- line_discount_sum: -2.50
- receipt discount_total: -2.50
- expected_total: 25.11

Adding both discounts would double-count the same discount and incorrectly
produce 22.61.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


CENT = Decimal("0.01")


@dataclass(frozen=True)
class DiscountContractCase:
    name: str
    line_total_sum: Decimal
    line_discount_sum: Decimal
    discount_total: Decimal
    expected_total: Decimal


def cents(value: str) -> Decimal:
    return Decimal(value).quantize(CENT)


def is_closed(value: Decimal, expected: Decimal) -> bool:
    return value.quantize(CENT) == expected.quantize(CENT)


def evaluate_variant_b(case: DiscountContractCase) -> dict[str, Decimal | bool]:
    using_line_discount = (case.line_total_sum + case.line_discount_sum).quantize(CENT)
    using_receipt_discount = (case.line_total_sum + case.discount_total).quantize(CENT)
    using_both_discounts = (
        case.line_total_sum + case.line_discount_sum + case.discount_total
    ).quantize(CENT)

    line_discount_closes = is_closed(using_line_discount, case.expected_total)
    receipt_discount_closes = is_closed(using_receipt_discount, case.expected_total)
    both_discounts_close = is_closed(using_both_discounts, case.expected_total)

    return {
        "using_line_discount": using_line_discount,
        "using_receipt_discount": using_receipt_discount,
        "using_both_discounts": using_both_discounts,
        "line_discount_closes": line_discount_closes,
        "receipt_discount_closes": receipt_discount_closes,
        "both_discounts_close": both_discounts_close,
        "contract_ok": (line_discount_closes or receipt_discount_closes)
        and not both_discounts_close,
    }


def main() -> None:
    case = DiscountContractCase(
        name="AH foto 14 discount double-representation",
        line_total_sum=cents("27.61"),
        line_discount_sum=cents("-2.50"),
        discount_total=cents("-2.50"),
        expected_total=cents("25.11"),
    )

    result = evaluate_variant_b(case)

    print("=== RECEIPT DISCOUNT CONTRACT VARIANT B ===")
    print("case                       :", case.name)
    print("line_total_sum             :", case.line_total_sum)
    print("line_discount_sum          :", case.line_discount_sum)
    print("receipt discount_total     :", case.discount_total)
    print("expected_total             :", case.expected_total)
    print("line_total + line_discount :", result["using_line_discount"])
    print("line_total + receipt_disc  :", result["using_receipt_discount"])
    print("line_total + both discounts:", result["using_both_discounts"])
    print("line_discount_closes       :", result["line_discount_closes"])
    print("receipt_discount_closes    :", result["receipt_discount_closes"])
    print("both_discounts_close       :", result["both_discounts_close"])

    if not result["contract_ok"]:
        raise SystemExit("DISCOUNT_CONTRACT_FAILED")

    print("DISCOUNT_CONTRACT_OK")


if __name__ == "__main__":
    main()
