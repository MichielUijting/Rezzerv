from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
HEAD_REVISION = "20260830_01"


def migrated_support_engine():
    database_path = Path(tempfile.mkdtemp(prefix="rezzerv-support-")) / "support.sqlite"
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
            "Alembic support fixture migration failed:\n"
            + result.stdout
            + result.stderr
        )
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}", future=True)
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != HEAD_REVISION:
        raise AssertionError(f"Expected Alembic revision {HEAD_REVISION}, got {revision}")
    return engine
