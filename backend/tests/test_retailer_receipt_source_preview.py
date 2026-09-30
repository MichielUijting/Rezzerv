from __future__ import annotations

import base64
from pathlib import Path

from app.integrations.retailer_receipts import RetailerReceiptEnvelope
from app.services.retailer_receipt_import_service import (
    _decode_source_snapshot_data_url,
    _sanitize_envelope_and_snapshot,
    _source_preview_path,
)


def _png_data_url(payload: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


def test_lidl_source_snapshot_is_removed_from_structured_receipt_payload() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"test-preview"
    envelope = RetailerReceiptEnvelope(
        provider="lidl",
        external_receipt_id="22000742902026090914942",
        receipt={
            "id": "22000742902026090914942",
            "totalAmount": "12.34",
            "products": [{"name": "Melk", "quantity": 1, "lineTotal": "1.25"}],
            "_sourceSnapshotDataUrl": _png_data_url(png),
        },
    )

    sanitized, snapshot = _sanitize_envelope_and_snapshot(envelope)

    assert snapshot == png
    assert "_sourceSnapshotDataUrl" not in sanitized.receipt
    assert sanitized.receipt["products"][0]["name"] == "Melk"


def test_source_snapshot_decoder_rejects_non_png_and_oversized_like_input() -> None:
    assert _decode_source_snapshot_data_url("data:text/plain;base64,SGVsbG8=") is None
    assert _decode_source_snapshot_data_url("data:image/png;base64,not-valid-base64") is None


def test_source_preview_path_is_companion_file() -> None:
    raw = Path("/tmp/household/raw-receipt.inhuis-receipt.json")
    assert _source_preview_path(raw) == Path(
        "/tmp/household/raw-receipt.inhuis-receipt.json.source-preview.png"
    )
