"""Contract tests for encrypted staging; no receipt or production DB writes."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.integrations.retailer_receipts import RetailerReceiptEnvelope
from app.services import retailer_import_queue as queue


def _lidl(receipt_id: str) -> RetailerReceiptEnvelope:
    return RetailerReceiptEnvelope(
        provider="lidl", external_receipt_id=receipt_id,
        receipt={"id": receipt_id, "products": [{"name": "Test", "quantity": 1}]},
    )


class _Rows:
    def __init__(self, result):
        self.result = result

    def mappings(self):
        return self

    def first(self):
        return self.result

    def one(self):
        assert self.result is not None
        return self.result


class _Connection:
    def __init__(self):
        self.rows = {}
        self.statements = []

    def execute(self, statement, parameters):
        sql = str(statement)
        self.statements.append((sql, parameters))
        identity = (parameters["household_id"], parameters["provider"],
                    parameters["external_receipt_id"], parameters["payload_sha256"])
        if "INSERT INTO retailer_import_queue" in sql:
            if identity in self.rows:
                return _Rows(None)
            self.rows[identity] = {"id": parameters["id"], "status": "pending"}
        elif "SELECT id,status FROM retailer_import_queue" not in sql:
            raise AssertionError("Unexpected database write or read")
        return _Rows(self.rows[identity])


class _Database:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.connection = _Connection()
        self.transactions = 0

    def begin(self):
        database = self

        class Transaction:
            def __enter__(self):
                database.transactions += 1
                return database.connection

            def __exit__(self, *_args):
                return None

        return Transaction()


def test_lidl_staging_is_encrypted_household_scoped_and_idempotent(monkeypatch):
    crypto = Fernet(Fernet.generate_key())
    monkeypatch.setattr(queue, "_fernet", lambda: crypto)
    db = _Database()
    first = queue.stage_confirmed_receipts(db, household_id="home-A", envelopes=[_lidl("87654321")])
    again = queue.stage_confirmed_receipts(db, household_id="home-A", envelopes=[_lidl("87654321")])
    other = queue.stage_confirmed_receipts(db, household_id="home-B", envelopes=[_lidl("87654321")])
    assert first == again
    assert first[0]["status"] == "pending"
    assert other[0]["queue_id"] != first[0]["queue_id"]
    assert db.transactions == 3
    assert len(db.connection.rows) == 2
    params = next(parameters for sql, parameters in db.connection.statements
                  if "INSERT INTO retailer_import_queue" in sql)
    assert "87654321" not in params["payload_ciphertext"]
    decrypted = json.loads(crypto.decrypt(params["payload_ciphertext"].encode()))
    assert decrypted["external_receipt_id"] == "87654321"
    assert params["household_id"] == "home-A"


def test_batch_rejects_invalid_input_before_db_write(monkeypatch):
    db = _Database()
    monkeypatch.setattr(queue, "_fernet", lambda: (_ for _ in ()).throw(AssertionError("no crypto expected")))
    with pytest.raises(ValueError, match="afzonderlijk"):
        queue.stage_confirmed_receipts(db, household_id="home-A", envelopes=[_lidl("12345678"), _lidl("87654321")])
    with pytest.raises(ValueError, match="Dubbel"):
        queue.stage_confirmed_receipts(db, household_id="home-A", envelopes=[_lidl("12345678"), _lidl("12345678")])
    with pytest.raises(ValueError, match="te grote"):
        queue.stage_confirmed_receipts(db, household_id="home-A", envelopes=[_lidl(str(n + 10000000)) for n in range(11)])
    assert db.transactions == 0


def test_queue_does_not_accept_non_postgres_or_ah():
    db = _Database()
    db.dialect = SimpleNamespace(name="sqlite")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        queue.stage_confirmed_receipts(db, household_id="home-A", envelopes=[_lidl("12345678")])
    db.dialect = SimpleNamespace(name="postgresql")
    with pytest.raises(ValueError, match="Alleen bevestigde"):
        queue.stage_confirmed_receipts(db, household_id="home-A", envelopes=[
            RetailerReceiptEnvelope(provider="ah", external_receipt_id="AH42", receipt={}),
        ])
    assert db.transactions == 0
