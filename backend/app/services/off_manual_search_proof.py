"""Kortlevend, onvervalsbaar bewijs van één door de server opgehaald OFF-zoekresultaat.

De OFF-zoekroute schrijft niets naar de database. Het bevestigingsverzoek mag
geen productinformatie van de browser vertrouwen. Een door dit backendproces
ondertekend ticket verbindt daarom bronartikel, GTIN en OFF-zoekgegevens.
Ticket vervalt na tien minuten en na een backendherstart (fail-closed).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.services.gtin_validation_service import is_valid_gtin

_PROOF_KEY = secrets.token_bytes(32)
_PROOF_TTL_SECONDS = 600
_MAX_TOKEN_CHARS = 12000
_PRODUCT_FIELDS = (
    "gtin", "product_name", "brand", "quantity", "category",
    "category_tags", "explicit_gpc_brick_code", "image_url",
)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_manual_off_proof(receipt_item_id: str, candidate: dict[str, Any]) -> str:
    """Server-only: issue a proof for one observed (not user-submitted) search hit."""
    source_id = str(receipt_item_id or "").strip()
    gtin = str(candidate.get("gtin") or "").strip()
    if not source_id or len(source_id) > 500 or not is_valid_gtin(gtin):
        return ""
    product = {
        field: candidate.get(field)
        for field in _PRODUCT_FIELDS
    }
    # Keep the token small even if an external provider includes excessive fields.
    try:
        encoded = json.dumps(
            {"v": 1, "receipt_item_id": source_id, "gtin": gtin,
             "expires": int(time.time()) + _PROOF_TTL_SECONDS, "product": product},
            ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return ""
    if len(encoded) > 6000:
        return ""
    payload = _encode(encoded)
    mac = _encode(hmac.new(_PROOF_KEY, payload.encode("ascii"), hashlib.sha256).digest())
    return payload + "." + mac


def verify_manual_off_proof(
    token: str, *, receipt_item_id: str, gtin: str,
) -> dict[str, Any]:
    """Reject tampering, expired searches, foreign receipts, invalid product data."""
    from app.services.gtin_validation_service import is_valid_gtin

    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_CHARS:
        raise ValueError("Zoek dit artikel opnieuw in OFF en probeer het nogmaals.")
    try:
        payload, mac = token.split(".")
        expected = hmac.new(_PROOF_KEY, payload.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_decode(mac), expected):
            raise ValueError("invalid proof signature")
        decoded = json.loads(_decode(payload))
    except (ValueError, TypeError, UnicodeError, base64.binascii.Error):
        raise ValueError("Ongeldig zoekbewijs. Zoek het artikel opnieuw in OFF.") from None

    if not isinstance(decoded, dict) or decoded.get("v") != 1:
        raise ValueError("Ongeldig zoekbewijs. Zoek het artikel opnieuw in OFF.")
    if (
        decoded.get("expires", 0) < int(time.time())
        or decoded.get("expires", 0) > int(time.time()) + _PROOF_TTL_SECONDS
    ):
        raise ValueError("Het zoekresultaat is verlopen. Zoek opnieuw in OFF.")
    if (
        decoded.get("receipt_item_id") != str(receipt_item_id or "").strip()
        or decoded.get("gtin") != str(gtin or "").strip()
        or not is_valid_gtin(gtin)
    ):
        raise ValueError("Dit zoekresultaat hoort niet bij het geselecteerde bonartikel.")

    product = decoded.get("product")
    if (
        not isinstance(product, dict)
        or product.get("gtin") != gtin
        or not str(product.get("product_name") or "").strip()
    ):
        raise ValueError("Dit OFF-product is niet geschikt om te koppelen.")
    return product
