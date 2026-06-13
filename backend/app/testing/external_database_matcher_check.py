from __future__ import annotations

from app.services.external_database_matchers import match_retailer_receipt_line


def run_check() -> dict[str, object]:
    return {
        "mexicaanse_kruidenm": match_retailer_receipt_line("lidl", "Mexicaanse kruidenm.", include_below_threshold=False),
        "taco_saus": match_retailer_receipt_line("lidl", "Taco saus", include_below_threshold=False),
    }
