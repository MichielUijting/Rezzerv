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


def test_kassa_new_and_inbox_share_one_route_instance():
    router = (ROOT / "frontend/src/app/router/AppRouter.jsx").read_text(encoding="utf-8")
    assert "{ path: '/kassa/*', element: <Protected><KassaPage /></Protected> }" in router
    assert "{ path: '/kassa', element: <Protected><KassaPage /></Protected> }" not in router
    assert "{ path: '/kassa/nieuw', element: <Protected><KassaPage /></Protected> }" not in router


def test_upload_fallback_remains_available_during_new_to_inbox_transition():
    kassa = (ROOT / "frontend/src/features/receipts/KassaPage.jsx").read_text(encoding="utf-8")
    router = (ROOT / "frontend/src/app/router/AppRouter.jsx").read_text(encoding="utf-8")
    assert "loadReceiptsWithUploadedFallback" in kassa
    assert "mergeUploadedReceiptIntoItems" in kassa
    assert "setFilters(DEFAULT_RECEIPT_FILTERS)" in kassa
    # Eén wildcardroute voorkomt een remount wanneer de uploadflow van
    # /kassa/nieuw terug navigeert naar /kassa. Daarmee blijven fallbackrecord,
    # geopende detailbon en receiptInboxFocusId onderdeel van dezelfde state.
    assert "'/kassa/*'" in router


def test_manual_kassa_upload_persists_unclassified_receipt_for_review():
    session_entrypoint = (ROOT / "backend/app/session_entrypoint.py").read_text(encoding="utf-8")
    assert 'MANUAL_RECEIPT_IMPORT_ROUTE = ("/api/receipts/import", "POST")' in session_entrypoint
    assert "_manual_receipt_import_context" in session_entrypoint
    assert 'kwargs["create_failed_receipt_table"] = True' in session_entrypoint
    assert "legacy_main.import_uploaded_receipt_payload = _import_uploaded_receipt_payload_with_manual_review_fallback" in session_entrypoint
    # De fallback is alleen actief binnen de request-context van de handmatige
    # Kassa-upload; andere importkanalen behouden hun bestaande beleid.
    assert "route_key == MANUAL_RECEIPT_IMPORT_ROUTE" in session_entrypoint
