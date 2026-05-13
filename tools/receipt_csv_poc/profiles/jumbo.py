from .base import ReceiptProfile


class JumboProfile(ReceiptProfile):
    profile_name = "jumbo"

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
