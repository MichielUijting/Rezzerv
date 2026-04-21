from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_SUPERMARKET_STOPWORDS = {
    "bio", "vers", "verse", "zak", "bak", "fles", "blik", "st", "stuk", "stuks",
    "g", "gram", "kg", "ml", "cl", "l", "ltr", "liter", "pak", "doos", "pot",
}

_SUPERMARKET_REPLACEMENTS = {
    "mexicaanse kruidenm": "mexicaanse kruidenmix",
    "jonge bladslaa": "jonge bladsla",
    "jonge bladsla zak": "jonge bladsla",
    "my aldi": "",
    "spaarpunten": "",
    "totaal voordeel": "",
    "pluspunten": "",
    " voordeel": " ",
}


def _ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_semantic_receipt_label(label: str | None, store_name: str | None = None) -> str:
    value = _ascii(str(label or "").strip().lower())
    value = value.replace("0", "o")
    for old, new in _SUPERMARKET_REPLACEMENTS.items():
        value = re.sub(r"\b" + re.escape(old) + r"\b", new, value)
    value = re.sub(r"\b\d+[x×]\d+[\.,]\d{2}\b", " ", value)
    value = re.sub(r"\b\d+[\.,]\d{2}\b", " ", value)
    value = re.sub(r"\b\d+(?:[\.,]\d+)?\s*(?:kg|g|gram|ml|cl|l|ltr|liter|st|stuk|stuks)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [t for t in value.split() if t and t not in _SUPERMARKET_STOPWORDS]
    compact_tokens: list[str] = []
    for token in tokens:
        if len(token) > 6 and token.endswith(("m", "n", "s")) and token[:-1] in {"kruidenmi", "bladsl"}:
            token = token[:-1]
        compact_tokens.append(token)
    if store_name and str(store_name).strip().lower() in {"lidl", "aldi", "plus", "jumbo"}:
        dedup: list[str] = []
        for token in compact_tokens:
            if not dedup or dedup[-1] != token:
                dedup.append(token)
        compact_tokens = dedup
    return " ".join(compact_tokens).strip()


def semantic_labels_match(left: str | None, right: str | None, store_name: str | None = None) -> bool:
    lval = normalize_semantic_receipt_label(left, store_name)
    rval = normalize_semantic_receipt_label(right, store_name)
    if not lval or not rval:
        return False
    if lval == rval:
        return True
    if lval in rval or rval in lval:
        if min(len(lval), len(rval)) >= 6:
            return True
    ratio = SequenceMatcher(None, lval, rval).ratio()
    threshold = 0.88 if str(store_name or "").strip().lower() in {"lidl", "aldi", "plus", "jumbo"} else 0.92
    return ratio >= threshold
