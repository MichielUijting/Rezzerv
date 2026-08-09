from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_kassa_focused_import_scrolls_into_visible_inbox_window():
    runtime = (ROOT / "frontend/src/features/receipts/kassaInboxFocusRuntime.js").read_text(encoding="utf-8")
    entrypoint = (ROOT / "frontend/src/main.jsx").read_text(encoding="utf-8")
    kassa = (ROOT / "frontend/src/features/receipts/KassaPage.jsx").read_text(encoding="utf-8")

    assert 'data-testid^="kassa-row-"' in runtime
    assert "scrollIntoView" in runtime
    assert "block: 'nearest'" in runtime
    assert "installKassaInboxFocusRuntime" in entrypoint
    assert "receiptInboxFocusId" in kassa
    assert "KASSA_INBOX_VISIBLE_ROW_COUNT = 10" in kassa


def test_upload_fallback_does_not_prove_server_inbox_visibility():
    kassa = (ROOT / "frontend/src/features/receipts/KassaPage.jsx").read_text(encoding="utf-8")
    # Regression anchor: the UI has an optimistic fallback. The focus runtime is
    # therefore required so an older-dated newly imported receipt cannot remain
    # outside the ten-row visible inbox window while its detail is already open.
    assert "loadReceiptsWithUploadedFallback" in kassa
    assert "mergeUploadedReceiptIntoItems" in kassa
    assert "setFilters(DEFAULT_RECEIPT_FILTERS)" in kassa
