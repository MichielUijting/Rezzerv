from decimal import Decimal
from pathlib import Path

from app.services.receipt_service import parse_receipt_content


IMAGE_PATH = Path("/app/data/receipts/raw/1/2026/07/d6417dfb8a5444ff9151c106fad22d0f-AH foto 12.jpeg")


def dec(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def main() -> None:
    if not IMAGE_PATH.exists():
        raise AssertionError(f"Missing AH12 fixture image: {IMAGE_PATH}")

    result = parse_receipt_content(
        IMAGE_PATH.read_bytes(),
        filename="AH foto 12.jpeg",
        mime_type="image/jpeg",
    )

    lines = result.lines or []

    line_sum = sum((dec(line.get("line_total")) for line in lines), Decimal("0.00"))
    line_discount_sum = sum((dec(line.get("discount_amount")) for line in lines), Decimal("0.00"))
    discount_total = dec(result.discount_total)
    total = dec(result.total_amount)
    net = (line_sum + line_discount_sum + discount_total).quantize(Decimal("0.01"))

    if result.store_name != "Albert Heijn":
        raise AssertionError(f"Expected Albert Heijn, got {result.store_name!r}")

    if result.parse_status != "approved":
        raise AssertionError(f"Expected approved, got {result.parse_status!r}")

    if total != Decimal("42.65"):
        raise AssertionError(f"Expected total 42.65, got {total}")

    if discount_total != Decimal("-22.24"):
        raise AssertionError(f"Expected discount_total -22.24, got {discount_total}")

    if len(lines) != 17:
        raise AssertionError(f"Expected 17 lines, got {len(lines)}")

    if net != total:
        raise AssertionError(
            f"Expected net to match total, got line_sum={line_sum}, "
            f"line_discount_sum={line_discount_sum}, discount_total={discount_total}, "
            f"net={net}, total={total}"
        )

    labels = [str(line.get("raw_label") or "").upper() for line in lines]

    blocked_prefixes = ("KRAS", "BBOX", "BONUS")
    blocked = [label for label in labels if label.startswith(blocked_prefixes)]
    if blocked:
        raise AssertionError(f"AH savings discount block leaked into product lines: {blocked}")

    if not any("KOOPZEGELS" in label for label in labels):
        raise AssertionError("Expected KOOPZEGELS value line to remain present")

    print("M2C2i-129B AH12 savings block selftest passed")


if __name__ == "__main__":
    main()
