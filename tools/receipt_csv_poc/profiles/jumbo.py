from .base import ReceiptProfile


class JumboProfile(ReceiptProfile):
    profile_name = "jumbo"
    merge_strategy = "safe_previous_product_jumbo"
    max_quantity_merge_distance = 2

    product_block_start_keywords = [
        "omschrijving",
        "producten",
        "aantal omschrijving",
    ]

    product_block_end_keywords = ReceiptProfile.product_block_end_keywords + [
        "te betalen",
        "uw korting",
        "pinbetaling",
    ]

    def _target_product_index(self, rows: list, quantity_index: int):
        # Conservative Jumbo rule: only merge with a nearby previous product.
        # Never scan further back across other product rows.
        return self._find_safe_previous_product_index(rows, quantity_index)
