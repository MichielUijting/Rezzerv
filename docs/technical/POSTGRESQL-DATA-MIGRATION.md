# PostgreSQL production-data migration

PR #351 introduced the controlled data-migration layer after the PostgreSQL schema and runtime cutovers. PR #352 advances that path to the receipt household-authority head and adds a strict recovery path for the real unversioned production SQLite shape. Neither PR performs the production cutover itself.

## Locked contract

- Alembic remains the only schema authority.
- The current locked head is `20260830_02`.
- SQLite working source and PostgreSQL target must both be at `20260830_02` before data copy.
- The canonical head still contains exactly 87 application tables.
- `alembic_version` is never copied from the immutable production source; the canonical working copy and PostgreSQL target obtain their own migration lineage from Alembic.
- Normal Rezzerv runtime startup is not part of the migration runner.
- No dual-write, SQLite fallback, runtime DDL or target schema creation is introduced.
- The immutable production snapshot is never stamped or upgraded in place.

## Receipt household authority at `20260830_02`

The receipt chain now has one canonical household parent:

- `receipt_sources.household_id -> household_registry.id`
- `raw_receipts.household_id -> household_registry.id`
- `receipt_tables.household_id -> household_registry.id`

The migration repairs the known historical receipt household drift and reconstructs only the deterministic `<household_id>-manual-upload` source parent when that exact historical anomaly is present. Unknown source references, unknown household references or any unrelated foreign-key drift remain fail-closed.

## Canonical rebuild for the unversioned production snapshot

The real production SQLite database is an unversioned historical runtime shape. It must not be assigned an Alembic revision that it never actually had. The maintenance entrypoint therefore performs a canonical rebuild instead of historical revision adoption:

```powershell
python -m app.maintenance.postgresql_legacy_production_adoption `
  --source C:\path\to\rezzerv-production-snapshot.sqlite `
  --working-copy C:\path\to\rezzerv-production-working-copy.sqlite `
  --allow-working-copy-reset `
  --report-json C:\path\to\rezzerv-legacy-adoption.json
```

The established command path remains stable, but its implementation now:

- opens the immutable source read-only;
- verifies the source SHA-256 before and after the operation;
- requires SQLite `integrity_check` to pass;
- classifies only the explicitly known receipt foreign-key drift;
- rejects unknown source IDs and unregistered household IDs;
- builds a completely fresh canonical SQLite database from the immutable baseline and the real Alembic history through `20260830_02`;
- requires exactly 87 canonical application tables;
- proves that every production table exists in the canonical head;
- proves that every production column maps to a canonical column;
- rejects any new target-only required column for which production data would have to be invented;
- requires shared canonical tables to be empty before production data is overlaid, so migration-owned rows can never be silently replaced;
- preserves canonical-only migration-owned data, including deterministic Alembic seed data;
- overlays the production rows only into their canonical shared tables;
- temporarily suppresses canonical SQLite triggers during the overlay to avoid side-effect rows, then restores the exact canonical trigger definitions;
- reconstructs only the deterministic manual-upload receipt source boundary;
- requires `integrity_check` and `foreign_key_check` to be green afterwards;
- requires the final schema to remain byte-equivalent to the freshly built canonical `20260830_02` schema;
- fingerprints every source row over its original production columns and verifies that all source rows survive;
- fingerprints production primary keys and verifies that every source PK survives;
- permits additional rows only where the canonical receipt recovery deliberately creates the manual-upload source;
- verifies that canonical-only migration-owned row counts are unchanged.

The production feasibility rehearsal on the frozen real snapshot proved this route with 59 production tables, 736 source rows, 46 known receipt-FK violations, 87 canonical tables, three reconstructed manual-upload sources and 418 Alembic-owned `external_product_index` seed rows. The immutable snapshot SHA remained unchanged throughout that proof.

## Production rehearsal sequence

1. Stop or otherwise freeze writes to the source SQLite database.
2. Create a database-consistent immutable SQLite snapshot with the SQLite backup API:

   ```powershell
   python -m app.maintenance.postgresql_data_migration_head snapshot `
     --source C:\path\to\rezzerv.db `
     --output C:\path\to\rezzerv-production-snapshot.sqlite
   ```

   Record the emitted SHA-256 and keep this snapshot immutable.

3. If the real production snapshot is unversioned, create a **separate canonical working copy** through the strict production recovery runner shown above. Never stamp or upgrade the immutable production snapshot itself.

   Require these recovery markers:

   ```text
   POSTGRESQL_LEGACY_ADOPTION_SOURCE_GREEN
   POSTGRESQL_LEGACY_ADOPTION_FK_DRIFT_GREEN
   POSTGRESQL_LEGACY_ADOPTION_CANONICAL_REBUILD_GREEN
   POSTGRESQL_LEGACY_ADOPTION_SOURCE_DATA_PRESERVED_GREEN
   POSTGRESQL_LEGACY_ADOPTION_MIGRATION_OWNED_DATA_GREEN
   POSTGRESQL_LEGACY_ADOPTION_HEAD_GREEN revision=20260830_02 tables=87
   POSTGRESQL_LEGACY_ADOPTION_GREEN
   ```

   Retain the JSON recovery report and the canonical working copy with the rehearsal artifacts.

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

The strict legacy recovery path is only for an **unversioned immutable production SQLite snapshot**. It does not waive integrity checks, does not treat arbitrary foreign-key violations as recoverable, and does not infer or stamp a historical Alembic revision onto production. Canonical schema and migration-owned data are always created by Alembic first; only proven production rows are overlaid afterwards.

A real production cutover is approved only after this exact route has succeeded on a newly frozen immutable snapshot of the real SQLite database and the resulting PostgreSQL database has passed the full application acceptance suite. If writes resume after a rehearsal, a later cutover must start from a new final snapshot; the rehearsal snapshot must not be reused as production truth.
