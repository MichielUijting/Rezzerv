"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker


_DEFAULT_SQLITE_DATABASE_URL = "sqlite:////app/data/rezzerv.db"
_ALLOWED_DATASTORE_POLICIES = {"compatibility", "postgresql-only"}
DATASTORE_POLICY = str(
    os.getenv("REZZERV_DATASTORE_POLICY", "compatibility") or "compatibility"
).strip().lower()
if DATASTORE_POLICY not in _ALLOWED_DATASTORE_POLICIES:
    raise RuntimeError(
        "REZZERV_DATASTORE_POLICY must be one of "
        f"{sorted(_ALLOWED_DATASTORE_POLICIES)!r}"
    )

_configured_database_url = str(os.getenv("DATABASE_URL", "") or "").strip()
if not _configured_database_url:
    if DATASTORE_POLICY == "postgresql-only":
        raise RuntimeError(
            "DATABASE_URL is required when REZZERV_DATASTORE_POLICY=postgresql-only"
        )
    _configured_database_url = _DEFAULT_SQLITE_DATABASE_URL

DATABASE_URL = _configured_database_url
SQLITE_RUNTIME_VOLUME = os.getenv("SQLITE_RUNTIME_VOLUME", "sqlite_data").strip() or "sqlite_data"


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw_value = str(os.getenv(name, default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}")
    return value


_database_url = make_url(DATABASE_URL)
# SQLAlchemy maps a bare postgresql:// URL to psycopg2 by default. Rezzerv's
# PostgreSQL foundation standardizes on psycopg 3 while continuing to accept
# the common driver-neutral URL form from deployment environments.
if _database_url.drivername == "postgresql":
    _engine_url = _database_url.set(drivername="postgresql+psycopg")
else:
    _engine_url = _database_url

DATASTORE_KIND = _engine_url.get_backend_name()
if DATASTORE_POLICY == "postgresql-only" and DATASTORE_KIND != "postgresql":
    raise RuntimeError(
        "REZZERV_DATASTORE_POLICY=postgresql-only requires a PostgreSQL DATABASE_URL; "
        f"configured datastore={DATASTORE_KIND!r}"
    )

SQLITE_DATABASE_PATH = None
engine_kwargs = {}

if DATASTORE_KIND == "sqlite":
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    sqlite_path = _engine_url.database
    if sqlite_path and sqlite_path != ":memory:":
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        SQLITE_DATABASE_PATH = sqlite_path
elif DATASTORE_KIND == "postgresql":
    connect_args = {
        "connect_timeout": _env_int("DATABASE_CONNECT_TIMEOUT_SECONDS", 10, minimum=1),
    }
    sslmode = str(os.getenv("DATABASE_SSLMODE", "")).strip()
    if sslmode:
        connect_args["sslmode"] = sslmode

    engine_kwargs.update(
        {
            "pool_pre_ping": True,
            "pool_size": _env_int("DATABASE_POOL_SIZE", 5, minimum=1),
            "max_overflow": _env_int("DATABASE_MAX_OVERFLOW", 10, minimum=0),
            "pool_timeout": _env_int("DATABASE_POOL_TIMEOUT_SECONDS", 30, minimum=1),
            "connect_args": connect_args,
        }
    )

engine = create_engine(_engine_url, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def get_runtime_datastore_info() -> dict:
    """Return non-secret datastore diagnostics suitable for runtime status output."""

    info = {
        "datastore": DATASTORE_KIND,
        "database_url": _engine_url.render_as_string(hide_password=True),
        "policy": DATASTORE_POLICY,
    }
    if DATASTORE_KIND == "sqlite":
        info["database"] = SQLITE_DATABASE_PATH or ":memory:"
        info["storage"] = SQLITE_RUNTIME_VOLUME
    elif DATASTORE_KIND == "postgresql":
        info["database"] = _engine_url.database
        info["host"] = _engine_url.host
        if _engine_url.port is not None:
            info["port"] = _engine_url.port
    return info
