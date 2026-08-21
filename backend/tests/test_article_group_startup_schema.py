import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = BACKEND_ROOT / "app" / "main.py"


def _assert_central_startup_wiring() -> None:
    source = MAIN_SOURCE.read_text(encoding="utf-8")
    module = ast.parse(source)
    top_level_calls = [
        node.value.func.id
        for node in module.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    ]

    assert "from app.services.article_group_store import ensure_article_group_schema" in source
    assert "ensure_household_articles_schema" in top_level_calls
    assert "ensure_article_group_schema" in top_level_calls
    assert top_level_calls.index("ensure_household_articles_schema") < top_level_calls.index(
        "ensure_article_group_schema"
    )


def _run_startup_probe(temporary_root: Path) -> subprocess.CompletedProcess[str]:
    database_path = temporary_root / "fresh-startup.db"
    receipt_storage_root = temporary_root / "receipts"
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "RECEIPT_STORAGE_ROOT": str(receipt_storage_root),
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )
    probe = '''
from sqlalchemy import inspect, text

from app.db import engine
from app.services.article_group_store import ensure_article_group_schema

with engine.begin() as connection:
    connection.execute(text("""
        CREATE TABLE household_articles (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            article_group_id TEXT
        )
    """))
    connection.execute(text("""
        CREATE TABLE purchase_import_lines (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            matched_household_article_id TEXT,
            selected_article_group_id TEXT
        )
    """))

ensure_article_group_schema()

with engine.connect() as connection:
    assert "article_groups" in inspect(connection).get_table_names()
    connection.execute(text("""
        SELECT pil.id, ag.name
        FROM purchase_import_lines pil
        LEFT JOIN household_articles ha
          ON ha.id = pil.matched_household_article_id
         AND ha.household_id = :household_id
        LEFT JOIN article_groups ag
          ON ag.id = COALESCE(pil.selected_article_group_id, ha.article_group_id)
         AND ag.household_id = :household_id
        WHERE pil.batch_id = :batch_id
    """), {"household_id": "0", "batch_id": "missing-batch"}).fetchall()
'''

    return subprocess.run(
        [sys.executable, "-c", probe],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_central_startup_creates_article_groups_before_purchase_import_query(tmp_path):
    _assert_central_startup_wiring()
    result = _run_startup_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    _assert_central_startup_wiring()
    with tempfile.TemporaryDirectory(prefix="rezzerv-article-groups-startup-") as directory:
        completed = _run_startup_probe(Path(directory))
    if completed.returncode != 0:
        raise SystemExit(completed.stdout + completed.stderr)
    print("ARTICLE_GROUPS_STARTUP_SCHEMA_GREEN")
