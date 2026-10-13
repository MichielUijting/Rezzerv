"""Test Picnic secret handling without introducing a new database engine.

The Inhuis PostgreSQL gate is authoritative. These tests use an in-memory
recording SQL-connection double for encryption, scope and state transitions.
"""
import pytest

from app.services import retailer_account_secure_store as shared
from app.services.picnic_account_secure_store import (
    save_picnic_auth, get_picnic_auth, delete_picnic_auth, picnic_status,
    reserve_picnic_sms_request,
)


class FakeResult:
    def __init__(self, value=None, rowcount=0):
        self.value = value
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self.value


class FakeConnection:
    def __init__(self, records):
        self.records = records

    def execute(self, statement, values):
        sql = str(statement).upper()
        key = (str(values["household_id"]), str(values["provider"]))
        prior = self.records.get(key)
        if "SELECT CREDENTIAL_CIPHERTEXT" in sql:
            return FakeResult(prior)
        if "INSERT INTO RETAILER_ACCOUNT_CREDENTIALS" in sql:
            self.records[key] = values["ciphertext"]
            return FakeResult(rowcount=1)
        if "UPDATE RETAILER_ACCOUNT_CREDENTIALS" in sql:
            if prior != values["prior_cipher"]:
                return FakeResult(rowcount=0)
            self.records[key] = values["next_cipher"]
            return FakeResult(rowcount=1)
        if "DELETE FROM RETAILER_ACCOUNT_CREDENTIALS" in sql:
            self.records.pop(key, None)
            return FakeResult(rowcount=int(prior is not None))
        raise AssertionError("Unexpected SQL in Picnic credentials test")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeEngine:
    def __init__(self):
        self.records = {}

    def begin(self):
        return FakeConnection(self.records)

    def connect(self):
        return FakeConnection(self.records)


def test_picnic_keys_encrypted_household_scoped_and_separate_from_ah(tmp_path, monkeypatch):
    monkeypatch.delenv("REZZERV_RETAILER_ACCOUNT_KEY", raising=False)
    monkeypatch.setenv("REZZERV_RETAILER_ACCOUNT_KEY_PATH", str(tmp_path / "account.key"))
    shared.reset_retailer_account_key_cache_for_tests()
    engine = FakeEngine()
    engine.records[("family-one", "ah")] = "untouched-ah-ciphertext"
    try:
        assert picnic_status(engine, "family-one")["connected"] is False
        save_picnic_auth(engine, "family-one", "pending-secret-key-123", pending_2fa=True)
        assert picnic_status(engine, "family-one")["verification_required"] is True
        assert picnic_status(engine, "family-one")["connected"] is False
        assert get_picnic_auth(engine, "family-two") is None
        assert reserve_picnic_sms_request(engine, "family-one") == "pending-secret-key-123"
        with pytest.raises(ValueError, match="minimaal één minuut"):
            reserve_picnic_sms_request(engine, "family-one")
        assert engine.records[("family-one", "ah")] == "untouched-ah-ciphertext"
        assert "pending-secret-key-123" not in engine.records[("family-one", "picnic")]
        save_picnic_auth(engine, "family-one", "verified-secret-key-456", pending_2fa=False)
        shared.reset_retailer_account_key_cache_for_tests()
        verified = get_picnic_auth(engine, "family-one")
        assert verified["auth_key"] == "verified-secret-key-456"
        assert verified["pending_2fa"] is False
        assert verified["pending_until"] is None
        assert picnic_status(engine, "family-one")["connected"] is True
        assert picnic_status(engine, "family-one")["receipt_import_enabled"] is False
        delete_picnic_auth(engine, "family-one")
        assert get_picnic_auth(engine, "family-one") is None
        assert engine.records[("family-one", "ah")] == "untouched-ah-ciphertext"
    finally:
        shared.reset_retailer_account_key_cache_for_tests()


def test_expired_sms_session_cannot_be_verified_or_reused(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timedelta, timezone

    monkeypatch.delenv("REZZERV_RETAILER_ACCOUNT_KEY", raising=False)
    monkeypatch.setenv("REZZERV_RETAILER_ACCOUNT_KEY_PATH", str(tmp_path / "account.key"))
    shared.reset_retailer_account_key_cache_for_tests()
    engine = FakeEngine()
    try:
        save_picnic_auth(engine, "family-one", "pending-secret-key-123", pending_2fa=True)
        cipher = engine.records[("family-one", "picnic")]
        payload = json.loads(shared._fernet().decrypt(cipher.encode("ascii")))
        payload["pending_until"] = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        engine.records[("family-one", "picnic")] = shared._fernet().encrypt(
            json.dumps(payload).encode("utf-8")
        ).decode("ascii")
        assert get_picnic_auth(engine, "family-one") is None
        assert picnic_status(engine, "family-one")["connected"] is False
        with pytest.raises(ValueError, match="verlopen"):
            reserve_picnic_sms_request(engine, "family-one")
    finally:
        shared.reset_retailer_account_key_cache_for_tests()


def test_sms_request_limit_of_three(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timedelta, timezone

    monkeypatch.delenv("REZZERV_RETAILER_ACCOUNT_KEY", raising=False)
    monkeypatch.setenv("REZZERV_RETAILER_ACCOUNT_KEY_PATH", str(tmp_path / "account.key"))
    shared.reset_retailer_account_key_cache_for_tests()
    engine = FakeEngine()
    try:
        save_picnic_auth(engine, "family-one", "pending-secret-key-123", pending_2fa=True)
        for index in range(3):
            assert reserve_picnic_sms_request(engine, "family-one") == "pending-secret-key-123"
            encrypted = engine.records[("family-one", "picnic")]
            state = json.loads(shared._fernet().decrypt(encrypted.encode("ascii")))
            state["sms_last_requested"] = (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat()
            engine.records[("family-one", "picnic")] = shared._fernet().encrypt(
                json.dumps(state).encode("utf-8")
            ).decode("ascii")
        with pytest.raises(ValueError, match="Maximum"):
            reserve_picnic_sms_request(engine, "family-one")
    finally:
        shared.reset_retailer_account_key_cache_for_tests()
