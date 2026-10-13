"""Picnic encrypted credential partition and 2FA pending-state contracts."""
from sqlalchemy import create_engine, text

from app.services import retailer_account_secure_store as shared
from app.services.picnic_account_secure_store import (
    save_picnic_auth, get_picnic_auth, delete_picnic_auth, picnic_status,
)


def test_picnic_keys_are_encrypted_household_scoped_and_not_ah(tmp_path, monkeypatch):
    monkeypatch.delenv("REZZERV_RETAILER_ACCOUNT_KEY", raising=False)
    monkeypatch.setenv("REZZERV_RETAILER_ACCOUNT_KEY_PATH", str(tmp_path / "account.key"))
    shared.reset_retailer_account_key_cache_for_tests()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE retailer_account_credentials (
                    household_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    credential_ciphertext TEXT NOT NULL,
                    expires_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY(household_id, provider)
                )
            """))
            conn.execute(text("""
                INSERT INTO retailer_account_credentials(household_id, provider, credential_ciphertext)
                VALUES ('family-one', 'ah', 'untouched-ah-ciphertext')
            """))
        assert picnic_status(engine, "family-one")["connected"] is False
        save_picnic_auth(engine, "family-one", "pending-secret-key-123", pending_2fa=True)
        assert picnic_status(engine, "family-one")["verification_required"] is True
        assert picnic_status(engine, "family-one")["connected"] is False
        assert get_picnic_auth(engine, "family-two") is None
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT provider, credential_ciphertext FROM retailer_account_credentials
                WHERE household_id='family-one' ORDER BY provider
            """)).fetchall()
        assert rows[0] == ("ah", "untouched-ah-ciphertext")
        assert rows[1][0] == "picnic"
        assert "pending-secret-key-123" not in rows[1][1]
        save_picnic_auth(engine, "family-one", "verified-secret-key-456", pending_2fa=False)
        shared.reset_retailer_account_key_cache_for_tests()
        assert get_picnic_auth(engine, "family-one") == {
            "auth_key": "verified-secret-key-456", "pending_2fa": False,
        }
        assert picnic_status(engine, "family-one")["connected"] is True
        assert picnic_status(engine, "family-one")["receipt_import_enabled"] is False
        delete_picnic_auth(engine, "family-one")
        assert get_picnic_auth(engine, "family-one") is None
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM retailer_account_credentials WHERE provider='ah'")).scalar() == 1
    finally:
        engine.dispose()
        shared.reset_retailer_account_key_cache_for_tests()
