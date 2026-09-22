from __future__ import annotations

import re
from typing import Any

_SUPPORTED_GTIN_LENGTHS = {8, 12, 13, 14}


def normalize_gtin_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def has_supported_gtin_length(value: Any) -> bool:
    normalized = normalize_gtin_digits(value)
    return normalized.isdigit() and len(normalized) in _SUPPORTED_GTIN_LENGTHS


def expected_gtin_check_digit(value_without_check_digit: Any) -> int | None:
    body = normalize_gtin_digits(value_without_check_digit)
    if len(body) not in {7, 11, 12, 13}:
        return None
    weighted_sum = sum(
        int(digit) * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(reversed(body))
    )
    return (10 - (weighted_sum % 10)) % 10


def is_valid_gtin(value: Any) -> bool:
    normalized = normalize_gtin_digits(value)
    if not normalized.isdigit() or len(normalized) not in _SUPPORTED_GTIN_LENGTHS:
        return False
    expected = expected_gtin_check_digit(normalized[:-1])
    return expected is not None and expected == int(normalized[-1])
