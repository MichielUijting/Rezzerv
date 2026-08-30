"""Dedicated datastore connection for Alembic schema authority.

Rezzerv runtime uses DATABASE_URL. PostgreSQL schema migrations require the
separately privileged MIGRATION_DATABASE_URL so the application role itself does
not need CREATE/ALTER/DROP rights. The historical single-credential behavior is
retained only for explicit SQLite compatibility/test/adoption runtimes.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


_DEFAULT_SQLITE_DATABASE_URL = "sqlite:////app/data/rezzerv.db"


def _runtime_database_url() -> str:
    configured = str(os.getenv("DATABASE_URL", "") or "").strip()
    if configured:
        return configured

    policy = str(
        os.getenv("REZZERV_DATASTORE_POLICY", "compatibility") or "compatibility"
    ).strip().lower()
    if policy == "postgresql-only":
        raise RuntimeError(
            "DATABASE_URL is required when REZZERV_DATASTORE_POLICY=postgresql-only"
        )
    return _DEFAULT_SQLITE_DATABASE_URL


def _migration_database_url() -> str:
    configured = str(os.getenv("MIGRATION_DATABASE_URL", "") or "").strip()
    if configured:
        return configured

    runtime_url = _runtime_database_url()
    runtime_backend = make_url(runtime_url).get_backend_name()
    if runtime_backend == "sqlite":
        return runtime_url
    if runtime_backend == "postgresql":
        raise RuntimeError(
            "MIGRATION_DATABASE_URL is required for PostgreSQL so schema authority "
            "does not silently reuse the runtime application credential"
        )
    raise RuntimeError(
        "Unsupported Rezzerv runtime datastore for migration configuration: "
        f"{runtime_backend!r}"
    )


MIGRATION_DATABASE_URL = _migration_database_url()


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw_value = str(os.getenv(name, default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}")
    return value


def _migration_engine_url():
    database_url = make_url(MIGRATION_DATABASE_URL)
    if database_url.drivername == "postgresql":
        return database_url.set(drivername="postgresql+psycopg")
    return database_url


_engine_url = _migration_engine_url()
_engine_kwargs = {"poolclass": NullPool}
if _engine_url.get_backend_name() == "sqlite":
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif _engine_url.get_backend_name() == "postgresql":
    connect_args = {
        "connect_timeout": _env_int("MIGRATION_DATABASE_CONNECT_TIMEOUT_SECONDS", 10, minimum=1),
    }
    sslmode = str(
        os.getenv("MIGRATION_DATABASE_SSLMODE", "")
        or os.getenv("DATABASE_SSLMODE", "")
        or ""
    ).strip()
    if sslmode:
        connect_args["sslmode"] = sslmode
    _engine_kwargs["connect_args"] = connect_args

migration_engine = create_engine(_engine_url, **_engine_kwargs)


def get_migration_datastore_info() -> dict:
    return {
        "datastore": _engine_url.get_backend_name(),
        "database_url": _engine_url.render_as_string(hide_password=True),
        "database": _engine_url.database,
        "host": _engine_url.host,
        "port": _engine_url.port,
    }
