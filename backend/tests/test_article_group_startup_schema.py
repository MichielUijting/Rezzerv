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

    assert "ensure_household_articles_schema" not in top_level_calls
    assert "ensure_article_group_schema" not in top_level_calls


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
    environment.pop("MIGRATION_DATABASE_URL", None)
    probe = '''
from sqlalchemy import inspect, text

from app.db import engine
from app.schema_migration_preflight import run_schema_migration_preflight

result = run_schema_migration_preflight()
assert result["dialect"] == "sqlite", result

with engine.connect() as connection:
    tables = set(inspect(connection).get_table_names())
    assert "household_articles" in tables
    assert "purchase_import_lines" in tables
    assert "article_groups" in tables
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


def test_central_startup_uses_migrated_article_group_schema(tmp_path):
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
