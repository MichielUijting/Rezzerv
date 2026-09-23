from __future__ import annotations

import inspect

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.receipt_service import ensure_default_receipt_sources


def test_default_receipt_sources_use_atomic_idempotent_upsert(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE receipt_sources (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    first = ensure_default_receipt_sources(engine, tmp_path / "receipts", "household-a")
    second = ensure_default_receipt_sources(engine, tmp_path / "receipts", "household-a")

    assert first == second
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, household_id, type, label, source_path, is_active "
                "FROM receipt_sources ORDER BY id"
            )
        ).mappings().all()

    assert [row["id"] for row in rows] == [
        "household-a-local-folder",
        "household-a-scan-folder",
    ]
    assert all(row["household_id"] == "household-a" for row in rows)
    assert all(int(row["is_active"]) == 1 for row in rows)

    source = inspect.getsource(ensure_default_receipt_sources)
    assert "ON CONFLICT (id) DO UPDATE" in source
    assert "SELECT id FROM receipt_sources WHERE id = :id LIMIT 1" not in source
