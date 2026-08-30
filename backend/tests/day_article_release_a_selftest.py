from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.day_article_service import (
    DIRECT_CONSUMPTION,
    STOCK,
    ensure_direct_location,
    get_default_inventory_handling,
    record_direct_consumption,
    set_default_inventory_handling,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
HEAD_REVISION = "20260830_01"


def _migrated_sqlite_engine(database_path: Path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    env["PYTHONPATH"] = str(BACKEND_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_INI),
            "upgrade",
            "head",
        ],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Alembic day-article Release A fixture migration failed:\n"
            + result.stdout
            + result.stderr
        )
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}", future=True)
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert revision == HEAD_REVISION
    return engine


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        engine = _migrated_sqlite_engine(Path(temp_dir) / "day-article-release-a.sqlite")
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO household_articles (
                    id,
                    household_id,
                    naam,
                    consumable,
                    updated_at
                ) VALUES (
                    'article-1',
                    'household-1',
                    'Verse broodjes',
                    1,
                    CURRENT_TIMESTAMP
                )
            """))
            ensure_authorization_foundation(conn)

            initial = get_default_inventory_handling(conn, "household-1", "article-1")
            assert initial["default_inventory_handling"] == STOCK

            updated = set_default_inventory_handling(
                conn,
                household_id="household-1",
                household_article_id="article-1",
                handling=DIRECT_CONSUMPTION,
                actor_user_id="admin-1",
            )
            assert updated["default_inventory_handling"] == DIRECT_CONSUMPTION

            direct = ensure_direct_location(conn, "household-1")
            assert direct["location"] == "Direct"
            assert direct["sublocation"] == "Direct"

            processed = record_direct_consumption(
                conn,
                household_id="household-1",
                household_article_id="article-1",
                quantity="2",
                idempotency_key="receipt-line-1",
                actor_user_id="member-1",
            )
            assert processed["quantity_received"] == "2"
            assert processed["quantity_consumed"] == "2"
            assert processed["net_inventory_change"] == "0"
            assert processed["idempotent_replay"] is False

            replay = record_direct_consumption(
                conn,
                household_id="household-1",
                household_article_id="article-1",
                quantity="2",
                idempotency_key="receipt-line-1",
                actor_user_id="member-1",
            )
            assert replay["idempotent_replay"] is True

            events = conn.execute(text("""
                SELECT event_type, quantity, space_id, sublocation_id
                FROM day_article_processing_events
                WHERE household_id = 'household-1' AND idempotency_key = 'receipt-line-1'
                ORDER BY event_type
            """)).mappings().all()
            assert len(events) == 2
            assert {row["event_type"] for row in events} == {"RECEIPT", "DIRECT_CONSUMPTION"}
            assert all(str(row["quantity"]) in {"2", "2.0", "2.00"} for row in events)
            assert all(row["space_id"] == direct["space_id"] for row in events)
            assert all(row["sublocation_id"] == direct["sublocation_id"] for row in events)

            inventory_count = conn.execute(text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='inventory'"
            )).scalar_one()
            assert inventory_count == 1
            inventory_rows = conn.execute(text(
                "SELECT COUNT(*) FROM inventory WHERE household_id = 'household-1'"
            )).scalar_one()
            assert inventory_rows == 0

        engine.dispose()

    print("DAY_ARTICLE_RELEASE_A_SELFTEST=PASS")


if __name__ == "__main__":
    main()
