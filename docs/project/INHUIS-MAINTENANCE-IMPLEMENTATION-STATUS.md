# PR 595 — implementation and verification status

TEST_LEVEL_PROVISIONAL: L

The backend, frontend, additive Alembic migration, PostgreSQL write barrier,
durable startup/request/worker authority, signed Windows host companion,
physical database/storage checks and verified backup/Windows-boot proof are
implemented. See [operation and deployment contract](INHUIS-MAINTENANCE-OPERATIONS.md).

The two initially failing Actions were repaired and both passed on
`aa5036309e1c8ba2575b26aa4885ce00a545dd6f`:

- Server maintenance isolated PostgreSQL validation;
- PostgreSQL data migration equivalence.

The PostgreSQL nullable-recipient parameter is explicitly typed; the canonical
schema authority includes the three additive maintenance tables. The local
legacy migration/rebuild selftests also passed.

Current implementation evidence is still being collected. The necessary
nullable SQL casts and exact schema/trigger-authority updates are explicit;
no check has been bypassed. Local route tests additionally prove 401/403
rejection before DML and that general status exposes no admin details. No final candidate
or successful full regression is implied by this document. Keep Draft until the
required preflight is green and follow the repository's exact-candidate gates.
No merge, deployment or production action is authorized by this PR.

The optional host-agent overlay is not applied by local PO testing. Missing
agent configuration disables starting the drain and never produces restart
permission. Physical Windows/host acceptance is an operational exercise after a
separate approved deployment; synthetic signed proofs in automated tests never
stand in for real host evidence at execution time.
