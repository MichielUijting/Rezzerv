from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.receipt_resend_inbound_source_household_guard import (
    install_receipt_resend_inbound_source_household_guard,
)


def _module():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE household_registry (id TEXT PRIMARY KEY, naam TEXT NOT NULL)"))
        conn.execute(
            text(
                """
                CREATE TABLE receipt_sources (
                    id TEXT PRIMARY KEY,
                    household_id TEXT,
                    type TEXT,
                    label TEXT,
                    source_path TEXT,
                    is_active INTEGER,
                    last_scan_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("INSERT INTO household_registry (id, naam) VALUES ('A', 'Huishouden A'), ('B', 'Huishouden B')"))
        conn.execute(
            text(
                """
                INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)
                VALUES
                    ('source-a', 'A', 'email', 'E-mail A', 'bon+a@example.test', 1),
                    ('source-inactive', 'A', 'email', 'Inactief', 'bon+inactive@example.test', 0),
                    ('source-orphan', 'MISSING', 'email', 'Orphan', 'bon+orphan@example.test', 1)
                """
            )
        )

    app = FastAPI()
    module = SimpleNamespace(
        app=app,
        engine=engine,
        text=text,
        build_receipt_source_response=lambda row: dict(row),
        resolve_household_email_source=lambda recipients: {"unsafe": True},
    )
    install_receipt_resend_inbound_source_household_guard(module)
    executed = {"count": 0}

    @app.post("/api/receipts/inbound-source-contract")
    def inbound_source_contract(payload: dict):
        source = module.resolve_household_email_source(payload.get("recipients") or [])
        executed["count"] += 1
        return {
            "source_id": source.get("id"),
            "household_id": source.get("household_id"),
            "route_address": source.get("route_address"),
        }

    return module, executed


def _assert_status(client: TestClient, recipients: list[str], expected: int) -> dict:
    response = client.post("/api/receipts/inbound-source-contract", json={"recipients": recipients})
    assert response.status_code == expected, response.text
    return response.json()


def main() -> None:
    module, executed = _module()
    client = TestClient(module.app)

    valid = _assert_status(client, ["BON+A@example.test"], 200)
    assert valid == {
        "source_id": "source-a",
        "household_id": "A",
        "route_address": "bon+a@example.test",
    }
    assert executed["count"] == 1

    with module.engine.begin() as conn:
        source_count_before = int(conn.execute(text("SELECT COUNT(*) FROM receipt_sources")).scalar_one())

    _assert_status(client, ["bon+unknown@example.test"], 400)
    _assert_status(client, ["bon+inactive@example.test"], 400)
    _assert_status(client, ["bon+orphan@example.test"], 400)
    _assert_status(client, [], 400)
    assert executed["count"] == 1

    with module.engine.begin() as conn:
        source_count_after = int(conn.execute(text("SELECT COUNT(*) FROM receipt_sources")).scalar_one())
        assert source_count_after == source_count_before
        conn.execute(
            text(
                """
                INSERT INTO receipt_sources (id, household_id, type, label, source_path, is_active)
                VALUES ('source-b-duplicate', 'B', 'email', 'Dubbel', 'bon+a@example.test', 1)
                """
            )
        )

    _assert_status(client, ["bon+a@example.test"], 409)
    assert executed["count"] == 1

    unrelated = client.get("/openapi.json")
    assert unrelated.status_code == 200
    print("receipt_resend_inbound_source_household_guard_contract: OK")


if __name__ == "__main__":
    main()
