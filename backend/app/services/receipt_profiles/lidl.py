from .base import BaseReceiptProfile


class LidlReceiptProfile(BaseReceiptProfile):
    profile_id = "lidl"
    store_aliases = ("lidl",)
