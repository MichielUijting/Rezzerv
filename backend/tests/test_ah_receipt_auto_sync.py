from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.integrations.retailer_accounts.ah import AHAccountSession, AHReceiptSummary
from app.integrations.retailer_receipts import RetailerReceiptEnvelope
from app.services import ah_receipt_sync_service as sync_service


class FakeClient:
    def __init__(self) -> None:
        self.detail_calls: list[str] = []

    def list_receipts(self, session, *, limit=100):
        return session, [
            AHReceiptSummary("known-1", "2026-09-29T12:00:00", 10.0),
            AHReceiptSummary("new-2", "2026-09-30T12:00:00", 12.0),
        ]

    def get_receipt_envelope(self, session, summary):
        self.detail_calls.append(summary.receipt_id)
        return session, RetailerReceiptEnvelope(
            provider="ah",
            external_receipt_id=summary.receipt_id,
            receipt={
                "id": summary.receipt_id,
                "dateTime": summary.date_time,
                "totalAmount": summary.total_amount,
                "products": [{"name": "Test", "quantity": 1, "lineTotal": summary.total_amount}],
            },
        )


def test_sync_fetches_details_only_for_new_ah_receipts(tmp_path, monkeypatch):
    engine = object()
    session = AHAccountSession(
        "access",
        "refresh",
        datetime.now(timezone.utc) + timedelta(hours=1),
    )
    saved_sessions: list[AHAccountSession] = []
    marked_receipts: list[set[str]] = []

    monkeypatch.setattr(sync_service, "get_ah_session", lambda _engine, _household_id: session)
    monkeypatch.setattr(
        sync_service,
        "save_ah_session",
        lambda _engine, _household_id, value: saved_sessions.append(value),
    )
    monkeypatch.setattr(
        sync_service,
        "get_known_ah_receipt_ids",
        lambda _engine, _household_id: {"known-1"},
    )
    monkeypatch.setattr(
        sync_service,
        "mark_ah_receipts_synced",
        lambda _engine, _household_id, values: marked_receipts.append(set(values)),
    )
    monkeypatch.setattr(
        sync_service,
        "touch_ah_sync",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("sync touch is niet verwacht")),
    )
    monkeypatch.setattr(
        sync_service,
        "ah_session_status",
        lambda _engine, _household_id: {"last_sync_at": "2026-09-30T12:05:00+00:00"},
    )

    imported: list[str] = []

    def fake_import(_engine, _receipt_storage_root, *, household_id, envelope):
        assert household_id == "household-a"
        imported.append(envelope.external_receipt_id)
        return {"receipt_id": envelope.external_receipt_id}

    monkeypatch.setattr(sync_service, "import_retailer_receipt", fake_import)
    client = FakeClient()

    result = sync_service.sync_ah_receipts(
        engine,
        tmp_path,
        household_id="household-a",
        limit=100,
        client=client,
    )

    assert client.detail_calls == ["new-2"]
    assert imported == ["new-2"]
    assert marked_receipts == [{"new-2"}]
    assert len(saved_sessions) == 2
    assert result["receipts_found"] == 2
    assert result["receipts_new"] == 1
    assert result["receipts_skipped_known"] == 1
    assert result["receipts_processed"] == 1
    assert result["last_sync_at"] == "2026-09-30T12:05:00+00:00"


def test_count_pending_ah_receipts_does_not_import(monkeypatch):
    engine = object()
    session = AHAccountSession(
        "access",
        "refresh",
        datetime.now(timezone.utc) + timedelta(hours=1),
    )
    saved_sessions: list[AHAccountSession] = []
    monkeypatch.setattr(sync_service, "get_ah_session", lambda _engine, _household_id: session)
    monkeypatch.setattr(
        sync_service,
        "save_ah_session",
        lambda _engine, _household_id, value: saved_sessions.append(value),
    )
    monkeypatch.setattr(
        sync_service,
        "get_known_ah_receipt_ids",
        lambda _engine, _household_id: {"known-1"},
    )
    monkeypatch.setattr(
        sync_service,
        "import_retailer_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("tellen mag niet importeren")),
    )

    client = FakeClient()
    result = sync_service.count_pending_ah_receipts(
        engine,
        household_id="household-a",
        client=client,
    )

    assert result == {
        "provider": "ah",
        "connected": True,
        "count_available": True,
        "pending_downloads": 1,
        "receipts_found": 2,
    }
    assert client.detail_calls == []
    assert saved_sessions == [session]
