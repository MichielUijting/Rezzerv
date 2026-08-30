# PostgreSQL foundation and production datastore policy

Rezzerv's canonical application runtime is PostgreSQL. The schema is owned by Alembic and normal application request paths are designed for a DML-only runtime role. SQLite remains available only as an explicit compatibility datastore for isolated tests, rehearsal and legacy SQLite adoption validation.

The production datastore cutover itself does not change application schema. Alembic head remains `20260830_01`.

## Runtime URL and policy contract

Rezzerv uses SQLAlchemy with psycopg 3. Both PostgreSQL URL forms are accepted:

```text
postgresql://user:password@host:5432/database
postgresql+psycopg://user:password@host:5432/database
```

A bare `postgresql://` URL is normalized internally to `postgresql+psycopg://`. Runtime datastore diagnostics redact credentials.

The canonical production stack sets:

```text
REZZERV_DATASTORE_POLICY=postgresql-only
```

Under this policy:

- `DATABASE_URL` is mandatory;
- the URL must resolve to PostgreSQL;
- a SQLite URL is rejected before normal runtime startup;
- there is no production fallback to `/app/data/rezzerv.db`.

The default `compatibility` policy intentionally retains the historical SQLite default for isolated tests and migration/adoption tooling that have not opted into the production policy. Tests that use SQLite should preferably set an explicit `DATABASE_URL=sqlite:...` so their datastore choice is visible.

PostgreSQL engine settings are controlled with these optional environment variables:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `10` | Driver connection timeout |
| `DATABASE_POOL_SIZE` | `5` | Persistent SQLAlchemy pool size |
| `DATABASE_MAX_OVERFLOW` | `10` | Temporary connections above the pool size |
| `DATABASE_POOL_TIMEOUT_SECONDS` | `30` | Wait for a pooled connection |
| `DATABASE_SSLMODE` | empty | psycopg SSL mode when the deployment requires it |

## Migration credential contract

PostgreSQL schema authority uses a separate `MIGRATION_DATABASE_URL`.

For PostgreSQL runtimes, `MIGRATION_DATABASE_URL` is mandatory. Rezzerv does not silently reuse `DATABASE_URL` for Alembic, because doing so would encourage granting schema mutation rights to the normal application role.

SQLite compatibility is the deliberate exception: when `DATABASE_URL` is explicitly SQLite and `MIGRATION_DATABASE_URL` is absent, migration/adoption tooling may use the same SQLite URL.

Migration-specific connection settings are controlled by:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `MIGRATION_DATABASE_CONNECT_TIMEOUT_SECONDS` | `10` | Alembic connection timeout |
| `MIGRATION_DATABASE_SSLMODE` | `DATABASE_SSLMODE` | Alembic psycopg SSL mode |

## Canonical Compose runtime

`docker-compose.yml` no longer selects SQLite and no longer mounts `./backend/data` as `/app/data`. It sets the production `postgresql-only` datastore policy and consumes explicit `DATABASE_URL` and `MIGRATION_DATABASE_URL` values from the deployment environment.

Consequently, starting only the canonical stack without valid database URLs is intentionally fail-closed.

For a local PostgreSQL development stack, combine the canonical application definition with the local PostgreSQL override:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.postgresql.yml \
  --profile postgresql \
  up -d --build
```

The local override starts PostgreSQL 17 and injects explicit PostgreSQL runtime and migration URLs into the backend. Its default local-only settings are:

```text
database: rezzerv
user: rezzerv
password: rezzerv-local-only
port: 5432
```

Override them through `REZZERV_POSTGRES_DB`, `REZZERV_POSTGRES_USER`, `REZZERV_POSTGRES_PASSWORD`, and `REZZERV_POSTGRES_PORT` as needed. These defaults are development credentials and are not a production privilege model.

## Production role separation

The production authority model uses separate credentials:

- a migration role with schema `USAGE`/`CREATE` for Alembic;
- an application role without schema `CREATE`, with only the runtime table/sequence privileges needed for DML.

`.github/workflows/postgresql-runtime-startup-schema-authority.yml` proves this model against PostgreSQL 17, including denial of runtime `CREATE TABLE`, migration to the canonical Alembic head, and representative DML-only request paths.

## CI acceptance

`.github/workflows/postgresql-foundation-validation.yml` proves independently that:

1. the production policy rejects a missing `DATABASE_URL`;
2. the production policy rejects SQLite;
3. explicit SQLite compatibility still imports and functions for isolated tooling;
4. PostgreSQL requires an explicit `MIGRATION_DATABASE_URL`;
5. runtime and migration PostgreSQL URLs normalize to psycopg 3;
6. the canonical Compose file contains no SQLite runtime URL or `/app/data` database mount;
7. a real PostgreSQL 17 service accepts the normal SQLAlchemy session/transaction foundation.

The full frontend regression and release-package runtime validation use the PostgreSQL Compose stack, so the end-to-end application and packaged runtime no longer depend on SQLite as their default datastore.
