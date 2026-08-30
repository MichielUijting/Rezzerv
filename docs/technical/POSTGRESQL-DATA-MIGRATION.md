# PostgreSQL production-data migration

PR #351 introduced the controlled data-migration layer after the PostgreSQL schema and runtime cutovers. PR #352 advances that path to the receipt household-authority head and adds a strict recovery path for the real unversioned production SQLite shape. Neither PR performs the production cutover itself.

## Locked contract

- Alembic remains the only schema authority.
- The current locked head is `20260830_02`.
- SQLite working source and PostgreSQL target must both be at `20260830_02` before data copy.
- The canonical head still contains exactly 87 application tables.
- `alembic_version` is never copied; PostgreSQL owns its own migration lineage.
- Normal Rezzerv runtime startup is not part of the migration runner.
- No dual-write, SQLite fallback, runtime DDL or target schema creation is introduced.
- The immutable production snapshot is never stamped or upgraded in place.

## Receipt household authority at `20260830_02`

The receipt chain now has one canonical household parent:

- `receipt_sources.household_id -> household_registry.id`
- `raw_receipts.household_id -> household_registry.id`
- `receipt_tables.household_id -> household_registry.id`

The migration repairs the known historical receipt household drift and reconstructs only the deterministic `<household_id>-manual-upload` source parent when that exact historical anomaly is present. Unknown source references, unknown household references or any unrelated foreign-key drift remain fail-closed.

## Production rehearsal sequence

1. Stop or otherwise freeze writes to the source SQLite database.
2. Create a database-consistent immutable SQLite snapshot with the SQLite backup API:

   ```powershell
   python -m app.maintenance.postgresql_data_migration_head snapshot `
     --source C:\path\to\rezzerv.db `
     --output C:\path\to\rezzerv-production-snapshot.sqlite
   ```

   Record the emitted SHA-256 and keep this snapshot immutable.

3. If the real production snapshot is unversioned, create and adopt a **separate working copy** through the strict production legacy-adoption runner:

   ```powershell
   python -m app.maintenance.postgresql_legacy_production_adoption `
     --source C:\path\to\rezzerv-production-snapshot.sqlite `
     --working-copy C:\path\to\rezzerv-production-working-copy.sqlite `
     --allow-working-copy-reset `
     --report-json C:\path\to\rezzerv-legacy-adoption.json
   ```

   The runner:

   - opens the immutable source read-only;
   - verifies the source SHA-256 before and after the operation;
   - requires SQLite `integrity_check` to pass;
   - classifies only the known receipt foreign-key drift patterns;
   - rejects unknown source IDs and household IDs;
   - probes disposable copies against the actual Alembic history;
   - requires one safe historical adoption point to upgrade to a schema byte-equivalent to a canonical SQLite `20260830_02` head;
   - upgrades only the working copy.

   Require the final working copy to report `20260830_02` and retain the JSON adoption report with the rehearsal artifacts.

4. If the source is already a valid versioned SQLite database, use only a separate working copy and bring that copy to `20260830_02` through the normal Alembic/schema-preflight route. Never mutate the immutable snapshot.

5. Create a fresh PostgreSQL migration target and run Alembic to `20260830_02` using the privileged migration credential.

6. Before any normal Rezzerv runtime starts against the target, run:

   ```powershell
   $env:MIGRATION_DATABASE_URL = '<privileged PostgreSQL URL>'
   python -m app.maintenance.postgresql_data_migration_head migrate `
     --source C:\path\to\rezzerv-production-working-copy.sqlite `
     --allow-target-reset `
     --report-json C:\path\to\rezzerv-postgresql-equivalence.json
   ```

7. Require every green marker, especially:

   ```text
   POSTGRESQL_DATA_MIGRATION_HEAD_GREEN revision=20260830_02
   POSTGRESQL_DATA_MIGRATION_TABLE_SET_GREEN tables=87
   POSTGRESQL_DATA_MIGRATION_EQUIVALENCE_GREEN tables=87
   POSTGRESQL_DATA_MIGRATION_GREEN
   ```

8. Run the locked-head PostgreSQL migration-foundation validation and require:

   ```text
   POSTGRESQL_RECEIPT_HOUSEHOLD_AUTHORITY_GREEN
   MIGRATION_FOUNDATION_REVISION_20260830_02_GREEN
   ```

9. Run the full application/frontend regression suite against the migrated PostgreSQL target before writes are reopened.

## What the importer proves

The importer opens SQLite read-only, runs `integrity_check` and `foreign_key_check`, and requires source and target to have the same locked Alembic head and the same exact application-table/column sets.

The target may contain migration-owned seed data created by Alembic, but it may not already contain runtime data in the guarded sentinel tables. With the explicit `--allow-target-reset` safety flag, the fresh target's application data is replaced transactionally while schema and constraints remain PostgreSQL/Alembic-owned.

Foreign-key dependencies are derived from the PostgreSQL target and loaded parent-first. Cross-table cycles fail closed. Self-referential rows are ordered parent-first from the actual self-FK contract.

Values are converted against the PostgreSQL target type rather than copied as raw SQLite representations:

- integer/string legacy Booleans become real PostgreSQL `BOOLEAN` values;
- timezone-aware targets receive UTC datetimes; naive legacy timestamps are interpreted as UTC;
- numerics use `Decimal` semantics rather than float conversion;
- binary values remain bytes;
- `NULL` remains `NULL`.

Explicit primary keys are preserved. PostgreSQL serial/identity sequences are repaired above the imported maximum so the first post-cutover insert cannot collide with an imported identifier.

## Equivalence proof

For every one of the 87 application tables the report contains:

- source and target row counts;
- a canonical SHA-256 multiset fingerprint of all rows;
- the primary-key definition;
- a canonical SHA-256 primary-key fingerprint when a PK exists.

Canonical hashing treats equivalent SQLite/PostgreSQL representations as equal, for example SQLite `1` versus PostgreSQL `TRUE`, and a legacy timestamp versus the same UTC `TIMESTAMPTZ` instant. A mismatch raises an error while the PostgreSQL transaction is still open, so the target replacement rolls back.

## Safety boundaries

These tools are deliberately not general synchronization utilities. A second migration into an already populated runtime target is rejected. A source below or above the locked head is rejected by the locked-head importer. A PostgreSQL target below or above the locked head is rejected. Unexpected Boolean/timestamp/numeric data is rejected rather than guessed.

The strict legacy adoption path is only for an **unversioned** immutable production SQLite snapshot. It does not waive integrity checks and does not treat arbitrary foreign-key violations as recoverable.

A real production cutover is approved only after this exact route has succeeded on a newly frozen immutable snapshot of the real SQLite database and the resulting PostgreSQL database has passed the full application acceptance suite. If writes resume after a rehearsal, a later cutover must start from a new final snapshot; the rehearsal snapshot must not be reused as production truth.
