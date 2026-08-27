# PostgreSQL foundation

This foundation adds PostgreSQL connectivity without switching Rezzerv's current runtime away from SQLite. The existing `docker-compose.yml` remains the default application stack until the later schema, migration, rehearsal, and cutover phases are complete.

## Driver and URL contract

Rezzerv uses SQLAlchemy with psycopg 3. Both of these URL forms are accepted:

```text
postgresql://user:password@host:5432/database
postgresql+psycopg://user:password@host:5432/database
```

A bare `postgresql://` URL is normalized internally to `postgresql+psycopg://`. Runtime datastore diagnostics redact credentials.

PostgreSQL engine settings are controlled with these optional environment variables:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `10` | Driver connection timeout |
| `DATABASE_POOL_SIZE` | `5` | Persistent SQLAlchemy pool size |
| `DATABASE_MAX_OVERFLOW` | `10` | Temporary connections above the pool size |
| `DATABASE_POOL_TIMEOUT_SECONDS` | `30` | Wait for a pooled connection |
| `DATABASE_SSLMODE` | empty | psycopg SSL mode when the deployment requires it |

## Local PostgreSQL service

Start only the foundation database with:

```bash
docker compose -f docker-compose.postgresql.yml --profile postgresql up -d postgres
```

The development-only defaults are:

```text
database: rezzerv
user: rezzerv
password: rezzerv-local-only
port: 5432
```

Override these through `REZZERV_POSTGRES_DB`, `REZZERV_POSTGRES_USER`, `REZZERV_POSTGRES_PASSWORD`, and `REZZERV_POSTGRES_PORT` as needed. The local password is not a production credential.

Do **not** point the full Rezzerv application at this PostgreSQL database yet. Several current runtime schema foundations still contain SQLite-specific DDL and introspection and will be migrated in the next phase.

## CI acceptance

`.github/workflows/postgresql-foundation-validation.yml` proves two things independently:

1. the existing SQLite connection/session/transaction path still works;
2. a real PostgreSQL 17 service accepts a psycopg 3 connection, `SessionLocal`, commit, rollback, pool disposal, and reconnect.

The PostgreSQL smoke test intentionally uses the driver-neutral `postgresql://` form to verify the psycopg 3 normalization contract.
