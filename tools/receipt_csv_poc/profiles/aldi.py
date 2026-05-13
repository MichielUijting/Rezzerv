from .base import ReceiptProfile


class AldiProfile(ReceiptProfile):
    profile_name = "aldi"

    product_block_start_keywords = [
        "omschrijving",
        "producten",
    ]

    product_block_end_keywords = ReceiptProfile.product_block_end_keywords + [
        "totaal eur",
        "betaling",
        "betaald",
    ]
