# PostgreSQL schema authority cutover

## PR2c scope

PR2c starts the controlled transition from runtime schema self-healing to
versioned Alembic migrations as the sole schema authority.

Locked base for this slice:

- `main`: `b17f7e81f13fd43f8df3e15b4f7704eecc9813a4`
- Alembic head at start: `20260827_02`
- first cut-over domain: `external_article_product_links`

This is deliberately not a PostgreSQL production cutover and it is not a full
runtime-portability claim.

## First authority cutover

`external_article_product_links` is now migration-owned:

- revision `20260827_01` owns the exact immutable SQLite baseline;
- revision `20260827_02` owns the canonical PostgreSQL table, constraints and
  indexes;
- the production external-link service no longer executes `CREATE TABLE` or
  `CREATE INDEX`;
- save/read paths no longer self-heal schema;
- the legacy-named `ensure_external_article_product_link_schema()` remains only
  as a temporary **inert compatibility shim** because `app.main` still calls
  that historical symbol during direct module imports;
- that shim performs no query, write or DDL and therefore owns no schema
  authority;
- the isolated contract test provisions its own SQLite schema fixture instead
  of relying on production DDL.

The compatibility shim and remaining `app.main` call should be removed together
in a later cleanup slice. The shim may never regain schema reads, writes or DDL.
The fail-closed runtime boundary is `app.schema_migration_preflight`, which runs
before Uvicorn imports the application in the production backend entrypoint.

## Migration before runtime

The backend runtime image now includes `alembic.ini` and the complete Alembic
chain. `app.runtime_preflight` runs schema migration/adoption before receipt
model warmup and before Uvicorn starts.

### Fresh SQLite

An empty SQLite database runs `alembic upgrade head` and is built from the
immutable baseline.

### Existing SQLite without Alembic history

Existing SQLite is never stamped blindly. Startup:

1. captures the same ordered `sqlite_master` schema contract used for PR2a;
2. compares it byte-for-byte with `alembic/baseline_sqlite.sql.gz`;
3. fails closed when the schemas differ and reports both SHA-256 values;
4. only after an exact match stamps revision `20260827_01`;
5. upgrades to Alembic head.

This preserves the PR2a rule that an unknown or drifted SQLite database may not
be silently adopted.

### PostgreSQL

A fresh or already-versioned PostgreSQL database runs `alembic upgrade head`.
A PostgreSQL database that already contains application tables but has no
Alembic history is rejected; PR2c does not invent an unsafe PostgreSQL adoption
path.

## CI contract

`PostgreSQL migration foundation validation` now proves:

1. a fresh SQLite database reaches Alembic head and exactly matches the immutable
   schema contract;
2. an existing unversioned SQLite database built from that contract is validated,
   stamped and upgraded without schema drift;
3. the external-link production service contains no table/index DDL and its
   historical compatibility hook is inert, including when the table is absent;
4. the isolated external-link functional contract stays green using a
   test-owned fixture;
5. PostgreSQL 17 reaches Alembic head with `external_article_product_links` and
   all four expected indexes present.

## Explicitly still out of scope

This first PR2c slice does **not** remove the broader runtime schema foundations.
Fresh inventory on the locked base identified at least these remaining areas:

- `server_session_service.py`: session table creation, SQLite introspection and
  upgrade/self-healing in authentication paths;
- `receipt_lifecycle_foundation_service.py`: PRAGMA/sqlite_master checks,
  ALTER TABLE, indexes, triggers and lifecycle reconciliation;
- `canonical_inventory_identity_service.py` and temporal inventory foundations:
  SQLite introspection, runtime unique-index creation and SQLite date semantics;
- `roles_v2_schema_foundation.py`: runtime ALTER TABLE, data normalization and
  SQLite `RAISE(ABORT, ...)` triggers;
- additional startup/service-owned DDL found by subsequent authority slices.

These areas must be cut over separately because they carry authentication,
receipt lifecycle, inventory identity and authorization invariants.

## Important semantic constraints

PR2c does not change the inventory location model. Existing inventory may remain
locationless when **Waar Inhuis** is enabled after inventory already exists. No
location or sublocation `NOT NULL` constraint is introduced here.

PR2c also does not claim that external-link business SQL is PostgreSQL-portable.
The service still contains SQLite-oriented query expressions such as `GLOB` and
`datetime(...)`; those belong to the later runtime-portability phase. The schema
authority cutover only ensures that runtime code no longer owns this table's DDL.

## End state

The migration program remains on course toward:

- Alembic as the sole production schema authority;
- no startup schema mutation;
- no service-owned DDL;
- PostgreSQL runtime only after all business SQL and invariants are portable and
  the migration/data-validation/rehearsal gates are green.
