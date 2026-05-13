from .base import ReceiptProfile


class LidlProfile(ReceiptProfile):
    profile_name = "lidl"

    product_block_start_keywords = [
        "omschrijving",
        "artikelen",
        "producten",
    ]

    product_block_end_keywords = ReceiptProfile.product_block_end_keywords + [
        "uw voordeel",
        "te betalen",
        "betaling pin",
    ]
