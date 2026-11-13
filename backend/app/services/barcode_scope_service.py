"""Read-only GS1 restricted-circulation scope hints for barcode identity.

A valid GTIN checksum does not prove global uniqueness. Restricted codes must
not be matched or created as global identities. A positive "global_candidate"
classification only means the known restricted prefixes were not detected;
it does NOT authenticate ownership or replace an explicit user confirmation.

This is a recognition guard, not a decoder for retailer price/weight barcodes.
Lidl restricted codes are reviewed per receipt item in Identificeren.
"""
from __future__ import annotations

import re
from typing import Any

_SUPPORTED_LENGTHS = {8, 12, 13, 14}


def classify_barcode_scope(value: Any) -> dict[str, str | bool]:
    """Classify a barcode's *candidate* scope without network or DB access.

    GTIN-12 and GTIN-14 use the GTIN-13 prefix after zero-expansion or
    removing the packaging indicator. Do not decode a restricted barcode's
    product number, weight, or price: that format is retailer-specific.
    """
    code = re.sub(r"[\s-]+", "", str(value or "").strip())
    if len(code) not in _SUPPORTED_LENGTHS or not code.isascii() or not code.isdigit():
        return {"scope": "invalid", "requires_retailer": False,
                "reason": "Geen syntactisch bruikbare productcode"}
    if len(code) == 13:
        prefix = code[:2]
    elif len(code) == 12:
        prefix = "0" + code[:1]
    elif len(code) == 14:
        prefix = code[1:3]
    else:
        # No claim about restricted GTIN-8 allocations based on only digits.
        prefix = ""
    if prefix == "02" or prefix in {str(n) for n in range(20, 30)}:
        return {"scope": "restricted", "requires_retailer": True,
                "reason": "GS1 restricted circulation: winkel- of gebiedscode"}
    return {"scope": "global_candidate", "requires_retailer": False,
            "reason": "Geen herkenbare restricted-circulation-prefix; globale uniciteit niet bewezen"}
