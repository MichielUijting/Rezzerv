# PostgreSQL schema authority cutover

## PR2c scope

PR2c starts the controlled transition from runtime schema self-healing to
versioned Alembic migrations as the sole schema authority.

Locked base for that slice:

- `main`: `b17f7e81f13fd43f8df3e15b4f7704eecc9813a4`
- Alembic head at start: `20260827_02`
- first cut-over domain: `external_article_product_links`

That slice was deliberately not a PostgreSQL production cutover and it was not a
full runtime-portability claim.

## First authority cutover: external article links

`external_article_product_links` is migration-owned:

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

## PR2d: server-session authority cutover

PR2d continues the same migration-first rule for `server_sessions`.

Locked base for this slice:

- `main`: `65caae1d5adc180c1fd918619d462ada96c421f5`;
- Alembic head at start: `20260827_02`;
- new authority revision: `20260828_01`;
- cut-over domain: `server_sessions` only.

The current canonical session contract contains eleven columns:

- `id`;
- `session_token_hash`;
- `user_id`;
- nullable `active_household_id`;
- `issued_at`;
- `expires_at`;
- `session_version`;
- `revoked_at`;
- `replaced_by_session_id`;
- `created_at`;
- `updated_at`.

It also requires `session_token_hash` to remain unique and
`idx_server_sessions_user_active(user_id, revoked_at, expires_at)` to exist.

Revision `20260828_01` owns three fail-closed paths:

1. **fresh/versioned SQLite without `server_sessions`**: Alembic creates the
   canonical table and index;
2. **versioned SQLite with the historical runtime table**: Alembic first proves
   the exact legacy contract, rejects unexpected foreign keys, views, triggers
   and indexes, copies every row into a canonical replacement table, proves row
   count and data equivalence, then makes `active_household_id` nullable;
3. **PostgreSQL**: revision `20260827_02` already created the canonical table, so
   revision `20260828_01` performs validation only and fails when the expected
   columns, nullability, uniqueness or active-session index drifted.

Malformed existing SQLite is rejected before schema mutation. PR2d does not
introduce a repair path for arbitrary or unknown session schemas.

The production `server_session_service.py` no longer contains `CREATE TABLE`,
`CREATE INDEX`, `ALTER TABLE`, `DROP TABLE`, SQLite PRAGMA schema inspection or
`sqlite_master` self-healing. The historical `ensure_server_session_schema()`
name remains temporarily as an inert compatibility shim because existing
business paths still call it. It performs no query, write or DDL.

## Migration before runtime

The backend runtime image includes `alembic.ini` and the complete Alembic chain.
`app.runtime_preflight` runs schema migration/adoption before receipt model
warmup and before Uvicorn starts.

### Fresh SQLite

An empty SQLite database runs `alembic upgrade head`. Revision `20260827_01`
builds the immutable 49-table baseline; later authority revisions may add only
explicitly migration-owned post-baseline objects. At PR2d head that extension is
exactly the `server_sessions` table plus `idx_server_sessions_user_active`.

The immutable baseline asset itself is not modified.

### Existing SQLite without Alembic history

Existing SQLite is never stamped blindly. Startup:

1. captures the same ordered `sqlite_master` schema contract used for PR2a;
2. compares it byte-for-byte with `alembic/baseline_sqlite.sql.gz`;
3. fails closed when the schemas differ and reports both SHA-256 values;
4. only after an exact match stamps revision `20260827_01`;
5. upgrades to Alembic head, including the PR2d server-session authority
   revision.

This preserves the PR2a rule that an unknown or drifted SQLite database may not
be silently adopted. In particular, PR2d does not widen adoption to accept an
unversioned database that already contains arbitrary runtime-created
`server_sessions` state.

### Existing versioned SQLite

A database already at revision `20260827_02` may contain `server_sessions`
because the historical runtime hook created it after migration adoption. PR2d
handles that exact historical contract explicitly and migrates it to the
nullable canonical contract with data-preservation checks.

### PostgreSQL

A fresh or already-versioned PostgreSQL database runs `alembic upgrade head`.
A PostgreSQL database that already contains application tables but has no
Alembic history remains rejected; the authority slices do not invent an unsafe
PostgreSQL adoption path.

## CI contract

`PostgreSQL migration foundation validation` now proves:

1. a fresh SQLite database reaches Alembic head while its baseline portion stays
   byte-for-byte equal to the immutable baseline and exactly the migration-owned
   session table/index are added;
2. an existing unversioned SQLite database built from the immutable contract is
   validated, stamped and upgraded to the same head;
3. a revision-02 SQLite database without `server_sessions` receives the canonical
   table through Alembic;
4. a revision-02 SQLite database with the exact historical NOT NULL
   `active_household_id` session table is rebuilt with all seeded data preserved;
5. a malformed revision-02 `server_sessions` table is rejected without advancing
   Alembic history or mutating that malformed table;
6. the external-link production service remains DDL-free and its historical hook
   remains inert;
7. the server-session production service contains no runtime schema mutation or
   SQLite schema-repair logic and its historical hook is inert;
8. PostgreSQL 17 reaches Alembic head with both external-link and server-session
   authority contracts present and valid.

## Explicitly still out of scope

The broader runtime schema foundations remain separate slices. Current known
areas include:

- `receipt_lifecycle_foundation_service.py`: PRAGMA/sqlite_master checks,
  ALTER TABLE, indexes, triggers and lifecycle reconciliation;
- `canonical_inventory_identity_service.py` and temporal inventory foundations:
  SQLite introspection, runtime unique-index creation and SQLite date semantics;
- `roles_v2_schema_foundation.py`: runtime ALTER TABLE, data normalization and
  SQLite `RAISE(ABORT, ...)` triggers;
- additional startup/service-owned DDL found by subsequent authority slices.

These areas must be cut over separately because they carry receipt lifecycle,
inventory identity and authorization invariants.

PR2d also does **not** change session authorization semantics, cookie behavior,
session rotation, account-context resolution or business queries. It only moves
the `server_sessions` schema lifecycle out of runtime code.

## Important semantic constraints

The authority program does not change the inventory location model. Existing
inventory may remain locationless when **Waar Inhuis** is enabled after inventory
already exists. No location or sublocation `NOT NULL` constraint is introduced
by these slices.

The program also does not yet claim that all business SQL is PostgreSQL-portable.
Services still contain SQLite-oriented query expressions; those belong to the
later runtime-portability phase. Schema authority only ensures that runtime code
no longer owns the migrated domain's DDL.

## End state

The migration program remains on course toward:

- Alembic as the sole production schema authority;
- no startup schema mutation;
- no service-owned DDL;
- PostgreSQL runtime only after all business SQL and invariants are portable and
  the migration/data-validation/rehearsal gates are green.
