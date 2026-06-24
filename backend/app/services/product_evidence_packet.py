from __future__ import annotations


def build_product_evidence_packet_dict(receipt_line_text: str | None, retailer_code: str | None = None) -> dict:
    return {
        "retailer_code": str(retailer_code or "").strip().lower(),
        "receipt_line_text": str(receipt_line_text or "").strip(),
        "matched": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
