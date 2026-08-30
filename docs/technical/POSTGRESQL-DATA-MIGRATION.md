# PostgreSQL production-data migration

PR #351 adds the controlled data-migration layer after the PostgreSQL schema and runtime cutovers. It does **not** perform the production cutover itself.

## Locked contract

- Alembic remains the only schema authority.
- SQLite source and PostgreSQL target must both be at `20260830_01`.
- The canonical head contains exactly 87 application tables.
- `alembic_version` is never copied; PostgreSQL owns its own migration lineage.
- Normal Rezzerv runtime startup is not part of the migration runner.
- No dual-write, SQLite fallback, runtime DDL or target schema creation is introduced.

## Production rehearsal sequence

1. Stop or otherwise freeze writes to the source SQLite database.
2. Create a database-consistent immutable SQLite snapshot with the SQLite backup API:

   ```powershell
   python -m app.maintenance.postgresql_data_migration snapshot `
     --source C:\path\to\rezzerv.db `
     --output C:\path\to\rezzerv-production-snapshot.sqlite
   ```

   Record the emitted SHA-256 and keep this snapshot immutable.

3. Make a separate working copy of that immutable snapshot. Run the existing SQLite schema-migration preflight on the **working copy**, never on the preserved snapshot. The preflight validates/adopts a valid legacy baseline and upgrades it through Alembic. Confirm `20260830_01`.

4. Create a fresh PostgreSQL migration target and run Alembic to `20260830_01` using the privileged migration credential.
5. Before any normal Rezzerv runtime starts against the target, run:

   ```powershell
   $env:MIGRATION_DATABASE_URL = '<privileged PostgreSQL URL>'
   python -m app.maintenance.postgresql_data_migration migrate `
     --source C:\path\to\rezzerv-production-working-copy.sqlite `
     --allow-target-reset `
     --report-json C:\path\to\rezzerv-postgresql-equivalence.json
   ```

6. Require every green marker, especially:

   ```text
   POSTGRESQL_DATA_MIGRATION_HEAD_GREEN revision=20260830_01
   POSTGRESQL_DATA_MIGRATION_TABLE_SET_GREEN tables=87
   POSTGRESQL_DATA_MIGRATION_EQUIVALENCE_GREEN tables=87
   POSTGRESQL_DATA_MIGRATION_GREEN
   ```

7. Run the canonical PostgreSQL migration-foundation validation and the application regression suite against the migrated target before writes are reopened.

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

This tool is deliberately not a general synchronization utility. A second migration into an already populated runtime target is rejected. A source below or above the locked head is rejected. A PostgreSQL target below or above the locked head is rejected. Unexpected Boolean/timestamp/numeric data is rejected rather than guessed.

A real production cutover is only approved after this exact path has succeeded on an immutable snapshot of the real SQLite database and the migrated PostgreSQL database has passed full application acceptance.
