from .base import ReceiptProfile


class JumboProfile(ReceiptProfile):
    profile_name = "jumbo"
    merge_strategy = "previous_or_next_product"

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

    def _target_product_index(self, rows: list, quantity_index: int) -> int | None:
        previous_index = self._find_previous_product_index(rows, quantity_index)
        if previous_index is not None:
            return previous_index
        return self._find_next_product_index(rows, quantity_index)
