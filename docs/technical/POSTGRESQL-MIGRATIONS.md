# PostgreSQL migration chain

## Status

PR2a introduces Rezzerv's canonical **versioned migration mechanism** without yet switching runtime schema authority away from the existing startup foundations.

Canonical source baseline for this migration root:

- Git `main`: `0ae8032e380eeb1093bea044cbbe97b17b3c14e1`
- Alembic root revision: `20260827_01`
- Alembic: `1.19.1`
- PostgreSQL driver: psycopg 3
- Captured SQLite schema: 998 lines / 45,511 bytes
- Captured SQLite schema SHA-256: `e75cb2c16e41cd69fa42d2ffdf98dad7f3af67147ed07289edc9caa6ad4fc8b7`

The exact immutable SQLite SQL snapshot is stored losslessly as `backend/alembic/baseline_sqlite.sql.gz`.

The existing application remains SQLite-first at runtime after PR2a. Production configuration and production data are not changed.

## What revision `20260827_01` means

The first immutable revision deliberately has different responsibilities per datastore:

| Datastore | `20260827_01` responsibility |
| --- | --- |
| SQLite | Exact schema baseline captured from the canonical Rezzerv runtime at the source commit above |
| PostgreSQL | Migration-lineage root only; no Rezzerv application tables yet |

This split is intentional. The current runtime schema still contains SQLite-specific PRAGMA/introspection, triggers, date expressions and release `ensure_*` logic. Copying those semantics blindly into PostgreSQL would turn the migration mechanism into a false portability claim.

PR2b must add the PostgreSQL application-schema baseline as the next immutable revision. After that, later revisions can become shared portable deltas.

## Fresh SQLite database

A fresh SQLite database can be built entirely from the immutable baseline:

```powershell
$env:PYTHONPATH = "backend"
$env:DATABASE_URL = "sqlite:///C:/temp/rezzerv-fresh.sqlite"
python -m alembic -c backend/alembic.ini upgrade head
```

The baseline revision refuses to run if application schema objects already exist. That fail-closed behavior prevents accidental replay of baseline DDL over an existing Rezzerv database.

## Existing SQLite database

An existing Rezzerv SQLite database must **not** run the baseline upgrade. The safe adoption sequence is:

1. capture its schema with `backend/tests/capture_schema_baseline.py`;
2. prove that capture is byte-for-byte equal to the decompressed immutable baseline and matches the recorded SHA-256;
3. only then stamp the database at `20260827_01`.

Example after the schema contract is proven:

```powershell
$env:PYTHONPATH = "backend"
$env:DATABASE_URL = "sqlite:///C:/path/to/existing-rezzerv.sqlite"
python -m alembic -c backend/alembic.ini stamp 20260827_01
```

Stamping writes migration history only. It does not replay baseline DDL.

## PostgreSQL in PR2a

PR2a proves that the Alembic environment, central `DATABASE_URL` handling and psycopg-3 connection work against a real PostgreSQL 17 service:

```powershell
$env:PYTHONPATH = "backend"
$env:DATABASE_URL = "postgresql://user:password@localhost:5432/rezzerv"
python -m alembic -c backend/alembic.ini upgrade head
```

At revision `20260827_01` this creates only Alembic migration history. It does **not** make an empty PostgreSQL database a runnable Rezzerv datastore yet.

## Runtime schema authority during PR2a

PR2a does not remove or bypass any current runtime schema foundation. The application can therefore continue to start exactly as before while the migration chain is introduced and verified.

The temporary dual-authority period is explicit:

- Alembic is the canonical **migration-history mechanism** from PR2a onward;
- legacy startup DDL/`ensure_*` remains runtime schema authority until the relevant schema has been moved into versioned migrations;
- no new production schema change should be added only as startup self-healing once a corresponding domain has been cut over to Alembic.

The end-state remains: versioned migrations are the sole production schema authority and startup schema mutation is removed.

## CI contract

`.github/workflows/postgresql-migration-foundation-validation.yml` proves three independent properties:

1. **Fresh SQLite baseline** — an empty SQLite file upgrades to `20260827_01` and exactly matches the immutable captured schema.
2. **Existing SQLite adoption** — the exact current runtime schema matches the baseline and can be stamped without replaying DDL.
3. **PostgreSQL lineage** — PostgreSQL 17 reaches `20260827_01` through psycopg 3 while creating no premature Rezzerv application tables.

Any baseline drift is a CI failure.

## Next slice: PR2b

PR2b should create the canonical PostgreSQL application-schema baseline. It must explicitly port, rather than mechanically translate:

- SQLite PRAGMA / `sqlite_master` introspection;
- integer 0/1 booleans;
- SQLite `datetime(...)` semantics;
- `COLLATE NOCASE` behavior;
- `INSERT OR IGNORE` behavior;
- SQLite `RAISE(ABORT, ...)` triggers;
- server-session schema upgrades;
- receipt lifecycle constraints/triggers;
- authorization/roles-v2 database invariants;
- canonical inventory identity indexes and constraints.

Production cutover and production data migration remain out of scope until the later migration, validation, rehearsal and cutover phases are complete.
