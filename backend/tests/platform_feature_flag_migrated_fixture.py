from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
HEAD_REVISION = "20260902_01"


def _assert_head(engine):
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != HEAD_REVISION:
        engine.dispose()
        raise AssertionError(f"Expected Alembic revision {HEAD_REVISION}, got {revision}")
    return engine


def migrated_platform_feature_flag_engine():
    """Use the canonical PostgreSQL test database when one is configured.

    The SQLite fallback is retained only for explicit migration-compatibility
    workflows that do not configure a PostgreSQL runtime URL.
    """
    configured_url = str(os.getenv("DATABASE_URL") or "").strip()
    if configured_url:
        engine = create_engine(configured_url, future=True)
        if engine.dialect.name == "postgresql":
            return _assert_head(engine)
        engine.dispose()

    database_path = Path(tempfile.mkdtemp(prefix="rezzerv-feature-flags-compat-")) / "feature-flags.sqlite"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    env.pop("MIGRATION_DATABASE_URL", None)
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
            "Alembic feature-flag SQLite compatibility migration failed:\n"
            + result.stdout
            + result.stderr
        )
    return _assert_head(
        create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}", future=True)
    )
