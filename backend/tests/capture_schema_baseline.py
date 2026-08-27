from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def dump_schema(database_path: Path) -> str:
    connection = sqlite3.connect(str(database_path))
    try:
        rows = connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_master
            WHERE sql IS NOT NULL
              AND name NOT LIKE 'sqlite_%'
            ORDER BY
              CASE type
                WHEN 'table' THEN 0
                WHEN 'view' THEN 1
                WHEN 'index' THEN 2
                WHEN 'trigger' THEN 3
                ELSE 4
              END,
              name
            """
        ).fetchall()
    finally:
        connection.close()

    statements: list[str] = []
    for object_type, name, table_name, sql in rows:
        normalized_sql = str(sql or "").strip().rstrip(";")
        if not normalized_sql:
            continue
        statements.append(f"-- {object_type}: {name} (table={table_name})")
        statements.append(normalized_sql + ";")
        statements.append("")
    return "\n".join(statements).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    print(dump_schema(args.database), end="")


if __name__ == "__main__":
    main()
