from decimal import Decimal

from app.receipt_ingestion.profiles.ah.corrections import _ah_repair_image_balance_from_reliable_lines


def _net(lines, discount_total=None):
    line_sum = sum(Decimal(str(line.get("line_total") or 0)) for line in lines)
    line_discount_sum = sum(Decimal(str(line.get("discount_amount") or 0)) for line in lines)
    receipt_discount = Decimal(str(discount_total or 0))
    return (line_sum + line_discount_sum + receipt_discount).quantize(Decimal("0.01"))


def test_ah10_image_balance_repair():
    reliable_lines = [
        "Albert Heijn Zielhorst",
        "1 OLIJFOLIE 4.79 B 1,09",
        "1 OLIJFOLIE AH BANANEN 1,45 4,79 B",
        "0,587K CONFERENCE 1,11",
        "Prijs per kg 1,89",
        "5 SUBTOTAAL 13,23",
        "BONUS AHEXCEVOOSMA -2,88",
        "JOUW VOORDEEL 2,88",
        "SUBTOTAAL 10,35",
        "10 KOOPZEGELS 1,00",
        "TOTAAL 11,35",
    ]

    lines = [
        {"raw_label": "TIJGER MATS", "normalized_label": "TIJGER MATS", "line_total": 1.09, "discount_amount": None, "producer_trace": {"raw_line": "TIJGER MATS 1,09"}},
        {"raw_label": "OLTJFOLTIE", "normalized_label": "OLTJFOLTIE", "line_total": 4.79, "discount_amount": None, "producer_trace": {"raw_line": "OLTJFOLTIE 4,79 B"}},
        {"raw_label": "OLIJFOLIE", "normalized_label": "OLIJFOLIE", "line_total": 4.79, "discount_amount": None, "producer_trace": {"raw_line": "1 OLIJFOLIE 4,79 B"}},
        {"raw_label": "AH BANANEN", "normalized_label": "AH BANANEN", "line_total": 1.45, "discount_amount": None, "producer_trace": {"raw_line": "1 AH BANANEN 1,45"}},
        {"raw_label": "10 KOOPZEGELS 1,00", "normalized_label": "KOOPZEGELS", "line_total": 1.00, "discount_amount": None, "producer_trace": {"raw_line": "10 KOOPZEGELS 1,00"}},
    ]

    repaired, discount_total, diagnostics = _ah_repair_image_balance_from_reliable_lines(
        reliable_lines=reliable_lines,
        lines=lines,
        store_name="Albert Heijn",
        total_amount=Decimal("11.35"),
        discount_total=None,
    )

    assert diagnostics is not None
    assert diagnostics["r9_m2c2i128_ah_image_balance_repair"]["applied"] is True
    assert any(line.get("raw_label") == "CONFERENCE" and Decimal(str(line.get("line_total"))) == Decimal("1.11") for line in repaired)
    assert sum(Decimal(str(line.get("discount_amount") or 0)) for line in repaired).quantize(Decimal("0.01")) == Decimal("-2.88")
    assert discount_total is None
    assert _net(repaired, discount_total) == Decimal("11.35")


if __name__ == "__main__":
    test_ah10_image_balance_repair()
    print("OK")
