# PostgreSQL schema authority cutover

## PR2c: external article-link authority

PR2c started the controlled transition from runtime schema self-healing to
versioned Alembic migrations as the sole schema authority.

Locked base for that slice:

- `main`: `b17f7e81f13fd43f8df3e15b4f7704eecc9813a4`;
- Alembic head at start: `20260827_02`;
- first cut-over domain: `external_article_product_links`.

`external_article_product_links` is migration-owned:

- revision `20260827_01` owns the exact immutable SQLite baseline;
- revision `20260827_02` owns the canonical PostgreSQL table, constraints and
  indexes;
- the production external-link service no longer executes `CREATE TABLE` or
  `CREATE INDEX`;
- save/read paths no longer self-heal schema;
- the legacy-named `ensure_external_article_product_link_schema()` remains only
  as an inert compatibility shim;
- isolated contract tests provision their own SQLite schema fixture instead of
  relying on production DDL.

The fail-closed runtime boundary is `app.schema_migration_preflight`, which runs
before Uvicorn imports the application in the production backend entrypoint.

## PR2d: server-session authority

PR2d continued the same migration-first rule for `server_sessions`.

Locked base for that slice:

- `main`: `65caae1d5adc180c1fd918619d462ada96c421f5`;
- Alembic head at start: `20260827_02`;
- new authority revision: `20260828_01`;
- cut-over domain: `server_sessions` only.

The canonical session contract contains eleven columns:

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
2. **versioned SQLite with the exact historical runtime table**: Alembic proves
   the legacy contract, copies every row into a canonical replacement table,
   proves row count/data equivalence and makes `active_household_id` nullable;
3. **PostgreSQL**: revision `20260827_02` already created the canonical table, so
   revision `20260828_01` validates the existing contract without mutation.

Malformed existing SQLite is rejected before mutation. The production
`server_session_service.py` contains no table/index creation, ALTER/DROP,
SQLite PRAGMA inspection or `sqlite_master` repair. Its historical schema hook
is inert.

## PR2e: receipt lifecycle authority

PR2e moves receipt lifecycle schema authority out of runtime code while retaining
receipt lifecycle **data/business reconciliation**.

Locked base for this slice:

- `main`: `a724c0c5659b1e1fbdfd7154672c44c71a7fb164`;
- Alembic head at start: `20260828_01`;
- new authority revision: `20260828_02`;
- cut-over domain: the existing receipt lifecycle contract only.

Unlike `server_sessions`, PR2e does not need to create a new post-baseline SQLite
table. The canonical receipt lifecycle objects were already present in the
immutable SQLite baseline and were ported to PostgreSQL by revision
`20260827_02`. Revision `20260828_02` is therefore deliberately
**validation-only** for this domain.

The validated receipt lifecycle tables are:

- `raw_receipts`;
- `receipt_tables`;
- `receipt_table_lines`.

The migration-owned explicit indexes are:

- partial unique `uq_raw_receipts_household_hash`, which reserves an active
  receipt hash while `deleted_at IS NULL`;
- `idx_receipt_tables_logical_receipt_key`;
- `idx_receipt_tables_workflow_state`;
- `idx_receipt_table_lines_logical_line_key`.

The migration-owned approval guard is:

- trigger `trg_receipt_tables_preserve_explicit_approval`;
- on PostgreSQL, its canonical trigger function
  `rezzerv_preserve_explicit_receipt_approval()`.

Revision `20260828_02` fails closed when this contract drifts:

1. **SQLite**: table column contracts, explicit receipt indexes and receipt
   triggers are compared with the immutable baseline contract. A canonical
   database is not mutated; only Alembic history advances;
2. **PostgreSQL**: table/column/nullability, lifecycle indexes and the explicit
   approval trigger/function are validated against the migration-owned contract;
3. unsupported dialects are rejected.

A missing lifecycle index or approval trigger is rejected. PR2e does not restore,
repair or silently recreate malformed receipt lifecycle schema at runtime.

### Runtime receipt boundary after PR2e

`receipt_lifecycle_foundation_service.py` no longer owns receipt schema. It
contains no receipt `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE`, trigger DDL,
SQLite PRAGMA schema inspection or `sqlite_master` repair.

The historical names remain temporarily as inert compatibility shims:

- `ensure_receipt_lifecycle_foundation_schema()`;
- `ensure_explicit_approval_guard_trigger()`.

They execute no query, write or DDL.

The following logic intentionally remains runtime business/data logic:

- backfilling a missing stable `logical_receipt_key` on historical rows;
- backfilling a missing stable `logical_line_key`;
- mapping pre-semantic deleted receipt rows to `legacy_deleted` without inventing
  archive/remove intent;
- reconciling technical parser status back to an already persisted explicit user
  approval;
- applying `return_to_kassa` and `archive` lifecycle actions.

This distinction is intentional: Alembic owns schema/invariants; services may
still reconcile valid persisted data under that canonical schema.

### Explicit test boundary

Isolated unit tests that deliberately build minimal SQLite tables no longer rely
on production self-healing. They install the SQLite approval guard explicitly via
a test-only fixture.

The production receipt-inventory chain also follows the real migration-first
boundary. Before importing `app.main` against its temporary SQLite database, the
test runs the real Alembic chain to head. This ensures the production-chain test
contains migration-owned objects such as receipt lifecycle and external-link
schema without reintroducing service-owned DDL.

## Migration before runtime

The backend runtime image includes `alembic.ini` and the complete Alembic chain.
`app.runtime_preflight` runs schema migration/adoption before receipt model
warmup and before Uvicorn starts.

### Fresh SQLite

An empty SQLite database runs `alembic upgrade head`. Revision `20260827_01`
builds the immutable 49-table baseline. The post-baseline SQLite schema adds only
explicit migration-owned objects. At PR2e head the additional table/index remains
exactly:

- `server_sessions`;
- `idx_server_sessions_user_active`.

Receipt lifecycle objects remain part of the unchanged immutable baseline; PR2e
validates them and does not add a second copy.

The immutable baseline asset itself remains unchanged with SHA-256:

`e75cb2c16e41cd69fa42d2ffdf98dad7f3af67147ed07289edc9caa6ad4fc8b7`

### Existing SQLite without Alembic history

Existing SQLite is never stamped blindly. Startup:

1. captures the ordered `sqlite_master` schema contract;
2. compares it byte-for-byte with `alembic/baseline_sqlite.sql.gz`;
3. fails closed when the schemas differ and reports both SHA-256 values;
4. only after an exact match stamps revision `20260827_01`;
5. upgrades through the server-session authority slice and the PR2e receipt
   lifecycle validation revision.

This preserves the rule that an unknown or drifted SQLite database may not be
silently adopted.

### Existing versioned SQLite

A versioned SQLite database follows the explicit Alembic lineage. The server
session slice still handles its exact historical runtime-created variant. The
receipt lifecycle slice does not contain a generic repair path: the already
migration-owned receipt contract must validate exactly.

### PostgreSQL

A fresh or already-versioned PostgreSQL database runs `alembic upgrade head`.
Revision `20260827_02` creates the canonical PostgreSQL application schema;
revisions `20260828_01` and `20260828_02` then validate their respective authority
contracts. A PostgreSQL database that already contains application tables but has
no Alembic history remains rejected.

## CI contract at PR2e

The migration and receipt gates prove, among other things:

1. fresh SQLite reaches revision `20260828_02` while the immutable baseline
   portion remains byte-for-byte unchanged;
2. existing unversioned SQLite built from the exact immutable baseline is
   validated, stamped and upgraded;
3. the server-session migration paths remain intact and are tested against their
   own revision `20260828_01` rather than a moving global head;
4. canonical SQLite receipt schema survives revision `20260828_02` without
   receipt-schema mutation;
5. a missing receipt lifecycle index is rejected without repair or Alembic
   revision advance;
6. a missing receipt approval trigger is rejected without repair or Alembic
   revision advance;
7. production external-link, server-session and receipt lifecycle services remain
   free of their migrated runtime schema authority;
8. focused receipt lifecycle/approval behavior remains green with explicit test
   fixtures;
9. the production receipt-inventory chain starts from an Alembic-migrated
   temporary database rather than service-owned schema creation;
10. PostgreSQL 17 reaches head with external-link, server-session and receipt
    lifecycle authority contracts present and valid.

## Explicitly still out of scope

The broader runtime schema foundations remain separate slices. Current known
areas include:

- `canonical_inventory_identity_service.py` and temporal inventory foundations:
  SQLite introspection, runtime unique-index creation and SQLite date semantics;
- `roles_v2_schema_foundation.py`: runtime ALTER TABLE, data normalization and
  SQLite `RAISE(ABORT, ...)` triggers;
- additional startup/service-owned DDL found by subsequent authority audits.

These areas must be cut over separately because they carry inventory identity,
temporal and authorization invariants.

PR2e does **not** change receipt approval semantics, archive/remove semantics,
reimport lineage, inventory-event reversal rules, session behavior, authorization
or frontend lifecycle choices. Its purpose is the schema-authority boundary plus
the test-boundary changes required by that migration-first architecture.

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
