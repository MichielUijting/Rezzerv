"""Static/import contract for the PostgreSQL-only production datastore cutover."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent


def _run_python(code: str, *, env: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    child_env = dict(os.environ)
    for key, value in env.items():
        if value is None:
            child_env.pop(key, None)
        else:
            child_env[key] = value
    existing_pythonpath = str(child_env.get("PYTHONPATH") or "").strip()
    child_env["PYTHONPATH"] = str(_BACKEND_ROOT) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT,
        env=child_env,
        text=True,
        capture_output=True,
        check=False,
    )


def _expect_failure(code: str, *, env: dict[str, str | None], fragment: str) -> None:
    result = _run_python(code, env=env)
    combined = result.stdout + result.stderr
    assert result.returncode != 0, combined
    assert fragment in combined, combined


def _expect_success(code: str, *, env: dict[str, str | None], marker: str) -> None:
    result = _run_python(code, env=env)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert marker in combined, combined


def _assert_runtime_policy_contract() -> None:
    _expect_failure(
        "import app.db",
        env={
            "DATABASE_URL": None,
            "REZZERV_DATASTORE_POLICY": "postgresql-only",
        },
        fragment="DATABASE_URL is required when REZZERV_DATASTORE_POLICY=postgresql-only",
    )
    print("POSTGRESQL_PRODUCTION_DATABASE_URL_REQUIRED_GREEN")

    _expect_failure(
        "import app.db",
        env={
            "DATABASE_URL": "sqlite:///:memory:",
            "REZZERV_DATASTORE_POLICY": "postgresql-only",
        },
        fragment="requires a PostgreSQL DATABASE_URL",
    )
    print("POSTGRESQL_PRODUCTION_SQLITE_REJECTED_GREEN")

    _expect_success(
        "from app.db import DATASTORE_KIND; assert DATASTORE_KIND == 'sqlite'; "
        "print('SQLITE_EXPLICIT_COMPATIBILITY_GREEN')",
        env={
            "DATABASE_URL": "sqlite:///:memory:",
            "REZZERV_DATASTORE_POLICY": "compatibility",
        },
        marker="SQLITE_EXPLICIT_COMPATIBILITY_GREEN",
    )

    _expect_success(
        "from app.db import DATASTORE_KIND, DATASTORE_POLICY, engine; "
        "assert DATASTORE_KIND == 'postgresql'; "
        "assert DATASTORE_POLICY == 'postgresql-only'; "
        "assert engine.dialect.driver == 'psycopg'; "
        "print('POSTGRESQL_PRODUCTION_RUNTIME_POLICY_GREEN')",
        env={
            "DATABASE_URL": "postgresql://runtime:runtime@127.0.0.1:5432/rezzerv",
            "REZZERV_DATASTORE_POLICY": "postgresql-only",
        },
        marker="POSTGRESQL_PRODUCTION_RUNTIME_POLICY_GREEN",
    )


def _assert_migration_credential_contract() -> None:
    _expect_success(
        "from app.migration_db import migration_engine; "
        "assert migration_engine.dialect.name == 'sqlite'; "
        "print('SQLITE_MIGRATION_COMPATIBILITY_GREEN')",
        env={
            "DATABASE_URL": "sqlite:///:memory:",
            "MIGRATION_DATABASE_URL": None,
            "REZZERV_DATASTORE_POLICY": "compatibility",
        },
        marker="SQLITE_MIGRATION_COMPATIBILITY_GREEN",
    )

    _expect_failure(
        "import app.migration_db",
        env={
            "DATABASE_URL": "postgresql://runtime:runtime@127.0.0.1:5432/rezzerv",
            "MIGRATION_DATABASE_URL": None,
            "REZZERV_DATASTORE_POLICY": "postgresql-only",
        },
        fragment="MIGRATION_DATABASE_URL is required for PostgreSQL",
    )
    print("POSTGRESQL_MIGRATION_URL_REQUIRED_GREEN")

    _expect_success(
        "from app.migration_db import migration_engine; "
        "assert migration_engine.dialect.name == 'postgresql'; "
        "assert migration_engine.dialect.driver == 'psycopg'; "
        "print('POSTGRESQL_MIGRATION_CREDENTIAL_SPLIT_GREEN')",
        env={
            "DATABASE_URL": "postgresql://runtime:runtime@127.0.0.1:5432/rezzerv",
            "MIGRATION_DATABASE_URL": "postgresql://migrator:migrator@127.0.0.1:5432/rezzerv",
            "REZZERV_DATASTORE_POLICY": "postgresql-only",
        },
        marker="POSTGRESQL_MIGRATION_CREDENTIAL_SPLIT_GREEN",
    )


def _assert_deployment_contract() -> None:
    compose = (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    override = (_REPO_ROOT / "docker-compose.postgresql.yml").read_text(encoding="utf-8")

    assert "REZZERV_DATASTORE_POLICY: postgresql-only" in compose
    assert "DATABASE_URL: ${DATABASE_URL:-}" in compose
    assert "MIGRATION_DATABASE_URL: ${MIGRATION_DATABASE_URL:-}" in compose
    assert "sqlite:////app/data/rezzerv.db" not in compose
    assert "./backend/data:/app/data" not in compose

    assert "postgresql://" in override
    assert "MIGRATION_DATABASE_URL:" in override
    assert "condition: service_healthy" in override
    print("POSTGRESQL_PRODUCTION_COMPOSE_CONTRACT_GREEN")


def main() -> None:
    _assert_runtime_policy_contract()
    _assert_migration_credential_contract()
    _assert_deployment_contract()
    print("POSTGRESQL_PRODUCTION_DATASTORE_CUTOVER_GREEN")


if __name__ == "__main__":
    main()
