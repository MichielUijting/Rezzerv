"""Dedicated datastore connection for Alembic schema authority.

Rezzerv runtime uses DATABASE_URL. Schema migrations may use the separately
privileged MIGRATION_DATABASE_URL so the application role itself does not need
CREATE/ALTER/DROP rights. When MIGRATION_DATABASE_URL is absent, the historical
single-credential behavior remains available for SQLite and transitional
installations.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


_DEFAULT_DATABASE_URL = "sqlite:////app/data/rezzerv.db"
MIGRATION_DATABASE_URL = (
    str(os.getenv("MIGRATION_DATABASE_URL", "") or "").strip()
    or str(os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL) or _DEFAULT_DATABASE_URL).strip()
)


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
