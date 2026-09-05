#!/usr/bin/env python3
"""PostgreSQL regression proof for the legacy household-members payload query.

This self-test intentionally extracts the SQL used by
``list_household_role_change_audit`` from ``app/main.py`` and executes that
exact product query against PostgreSQL.  It therefore catches SQLite-only SQL
such as ``datetime(created_at)`` without importing the full application.
"""

from __future__ import annotations

import ast
import os
import pathlib
import uuid

from sqlalchemy import create_engine, text


BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_PATH = BACKEND_ROOT / "app" / "main.py"
TARGET_FUNCTION = "list_household_role_change_audit"


def _product_audit_query() -> str:
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"), filename=str(MAIN_PATH))
    target = next(
        (node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == TARGET_FUNCTION),
        None,
    )
    if target is None:
        raise AssertionError(f"{TARGET_FUNCTION} not found in {MAIN_PATH}")

    candidates: list[str] = []
    for node in ast.walk(target):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func_name = node.func.id if isinstance(node.func, ast.Name) else None
        if func_name != "text":
            continue
        value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            sql = value.value
            if "FROM household_role_change_audit" in sql:
                candidates.append(sql)

    if len(candidates) != 1:
        raise AssertionError(
            f"expected exactly one household role-audit query in {TARGET_FUNCTION}, found {len(candidates)}"
        )
    return candidates[0]


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url.startswith("postgresql"):
        raise AssertionError("DATABASE_URL must point to PostgreSQL for this self-test")

    sql = _product_audit_query()
    if "ORDER BY" not in sql or "created_at" not in sql:
        raise AssertionError("household role-audit query no longer contains its chronological ordering contract")

    engine = create_engine(database_url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text(sql),
            {"household_id": str(uuid.uuid4()), "limit": 20},
        ).mappings().all()

    if rows:
        raise AssertionError("random household unexpectedly returned household role-audit rows")

    print("POSTGRESQL_HOUSEHOLD_MEMBERS_ROLE_AUDIT_QUERY_GREEN")


if __name__ == "__main__":
    main()
