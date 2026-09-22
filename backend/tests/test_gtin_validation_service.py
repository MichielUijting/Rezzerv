from app.services.gtin_validation_service import (
    expected_gtin_check_digit,
    has_supported_gtin_length,
    is_valid_gtin,
    normalize_gtin_digits,
)


def test_invalid_afwasborstel_off_code_is_rejected_by_checksum():
    assert normalize_gtin_digits("00181781") == "00181781"
    assert has_supported_gtin_length("00181781") is True
    assert expected_gtin_check_digit("0018178") == 5
    assert is_valid_gtin("00181781") is False
    assert is_valid_gtin("00181785") is True


def test_supported_gtin_lengths_use_same_checksum_rule():
    assert is_valid_gtin("8718265184886") is True
    assert is_valid_gtin("8712345678906") is True
    assert is_valid_gtin("12345678901231") is True
    assert is_valid_gtin("12345") is False
