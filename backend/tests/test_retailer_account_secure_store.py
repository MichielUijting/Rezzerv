from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.integrations.retailer_accounts.ah import AHAccountSession
from app.services import retailer_account_secure_store as store


def test_ah_session_ciphertext_and_key_survive_runtime_cache_reset(tmp_path, monkeypatch):
    key_path = tmp_path / "retailer.key"
    monkeypatch.delenv("REZZERV_RETAILER_ACCOUNT_KEY", raising=False)
    monkeypatch.setenv("REZZERV_RETAILER_ACCOUNT_KEY_PATH", str(key_path))
    store.reset_retailer_account_key_cache_for_tests()

    session = AHAccountSession(
        access_token="access-secret-value",
        refresh_token="refresh-secret-value",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        member_id="member-1",
    )

    ciphertext = store._fernet().encrypt(store._session_payload(session)).decode("ascii")
    assert "access-secret-value" not in ciphertext
    assert "refresh-secret-value" not in ciphertext
    assert key_path.exists()
    original_key = key_path.read_bytes()

    store.reset_retailer_account_key_cache_for_tests()
    loaded = store._decode_session(ciphertext)

    assert loaded.access_token == session.access_token
    assert loaded.refresh_token == session.refresh_token
    assert loaded.member_id == session.member_id
    assert loaded.expires_at == session.expires_at
    assert key_path.read_bytes() == original_key
