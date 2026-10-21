# PR 595 — runtime implementation checkpoint

TEST_LEVEL_PROVISIONAL: L

Development checkpoint, **not a completed maintenance feature**. Keep Draft;
do not merge, deploy or use this candidate as permission for server restart.

Implemented for validation:

- Additive Alembic-owned control, durable operations and actor audit tables.
- Outermost ASGI admission for all domain methods, including GET paths that can
  backfill. Exact infrastructure exceptions retain authentication, status and
  notification access. Admission and drain serialize on the same PostgreSQL row.
- Durable handoff before ZIP-import, Kassa diagnostic and testing worker threads
  start. Normal completion releases the operation; uncaught failure/cancellation
  retains unresolved evidence. No expiry or force-drain bypass.
- Announcement/start/cancellation/end messages through the existing household
  notification service and an authenticated global status projection/banner.
- Recovery permission on management routes, generation CAS, execution-time
  Alembic/database/process/prepared-transaction checks and repeated database
  identity comparison before release.
- Existing Platformbeheer → Herstel screen with maintenance controls.
- Isolated PostgreSQL integration tests and dedicated Actions workflow.

## Remaining blockers

- `restart_allowed` deliberately remains false. Physical host/volume authority,
  a verified recoverable backup and actual Windows boot evidence are not yet
  connected. A backend UUID identifies an instance, never a Windows reboot.
- Startup DML/provisioning and dynamic installer threads are not yet inside the
  durable writer authority. Direct CLI/other-process entrypoints also need an
  enforced boundary before complete writer coverage can be claimed.
- Full authentication/household/receipt-chain/Playwright/F7 evidence is missing.
- No final patchversion/exact-candidate approval or validated Windows PO script.
- Offline inbox delivery does not imply acknowledgement by every recipient.
- Parallel PRs 592/594 remain relevant to retailer imports/progress.

Local checks: 16 unit tests plus 3 subtests passed; frontend production build
passed; UI component reuse and Alembic-head-literal checks passed. Real
PostgreSQL tests require the dedicated isolated CI service and are not claimed
as passed locally. The full candidate remains incomplete.

A prepared database drain is not host restart approval. Complete these blockers
and full regression before offering a functional PO restart test.
