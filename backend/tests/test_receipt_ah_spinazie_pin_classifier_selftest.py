from app.services import receipt_service


def assert_not_footer(line: str) -> None:
    classification = receipt_service._classify_receipt_text_line(
        line,
        store_name="Albert Heijn",
        filename="AH foto 17.jpeg",
    )
    if classification == "footer_payment_tax":
        raise AssertionError(
            f"{line!r} was incorrectly classified as footer_payment_tax"
        )


def assert_extracts_spinazie() -> None:
    lines = [
        "AH en Gall&Gall Schuytgraaf",
        "AANTAL OMSCHRIJVING PRIJS BEDRAG",
        "2 KNORR LASAGN 3,49 6,98",
        "1 RUNDERGEHAKT 5,87",
        "1 AH SPINAZIE 2,19",
        "2 KOMKOMMER 0,99 1,98",
        "24 SUBTOTAAL 77,04",
        "TOTAAL. 81,25",
    ]

    extracted = receipt_service._extract_receipt_lines(
        lines,
        store_name="Albert Heijn",
        filename="AH foto 17.jpeg",
    )

    spinazie = [
        line for line in extracted
        if str(line.get("raw_label") or "").upper() == "AH SPINAZIE"
    ]

    if len(spinazie) != 1:
        raise AssertionError(
            f"Expected exactly one AH SPINAZIE line, got {len(spinazie)}: {extracted}"
        )

    line = spinazie[0]
    if float(line.get("line_total") or 0) != 2.19:
        raise AssertionError(f"Expected AH SPINAZIE total 2.19, got {line}")


def assert_payment_still_blocked() -> None:
    for line in [
        "PINNEN 81,25",
        "BETAALD MET:",
        "TERMINAL 123456",
        "BANKPAS 81,25",
    ]:
        classification = receipt_service._classify_receipt_text_line(
            line,
            store_name="Albert Heijn",
            filename="AH foto 17.jpeg",
        )
        if classification != "footer_payment_tax":
            raise AssertionError(
                f"{line!r} should remain footer_payment_tax, got {classification!r}"
            )


def main() -> None:
    assert_not_footer("1 AH SPINAZIE 2,19")
    assert_not_footer("1 PINDAKAAS 3,49")
    assert_not_footer("1 SPINAZIE 2,19")
    assert_extracts_spinazie()
    assert_payment_still_blocked()
    print("M2C2i-129A AH17 SPINAZIE classifier selftest passed")


if __name__ == "__main__":
    main()
