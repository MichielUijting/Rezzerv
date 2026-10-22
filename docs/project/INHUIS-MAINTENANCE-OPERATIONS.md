# Inhuis: veilige serveronderhoudsprocedure

PR 595 implements maintenance in **Platformbeheer → Herstel → Serveronderhoud**.
The backend requires `platform.recovery.manage`; household administrators,
Superusers without that technical permission, and the IP owner receive no
implicit technical privileges.

## Administrator flow

1. Enter the maintenance window, timezone and expected duration; announce it.
   Existing household notification inboxes receive the announcement. The signed-in
   global banner also covers technical accounts without a household. Offline
   delivery is an inbox projection, not a receipt/acknowledgement guarantee.
2. Select **Verwerkingen veilig stoppen**. A fresh, pinned Windows-agent heartbeat
   is required before this can close admission. Existing requests/worker handoffs
   finish; new domain requests and database writes are rejected. The screen polls
   and automatically attempts the final safety checks when operations reach zero.
3. Only an unexpired **Alle veiligheidscontroles zijn geslaagd** result permits
   the administrator to decide on a Windows restart. The application and host
   agent never restart Windows. If the display expires, refresh it.
4. Restart Windows yourself. After the existing Windows login/Docker startup,
   the app remains closed. The agent checks the new Windows boot, the actual
   database/storage, restored-backup fingerprint, installed image/version and both
   local/external frontend/backend routes. The screen automatically verifies a
   detected backend restart; this alone never proves a Windows restart.
5. Select **Onderhoud beëindigen en gebruikers toelaten**. The backend repeats
   all checks in the same locked transition before admission reopens and the
   existing inbox receives the completion message.

Errors, incomplete operations, missing/stale signatures and mismatched data
leave admission closed. There is no forced reboot, lease expiry or force-release.
An interrupted/crashed operation requires investigation and reconciliation using
its original domain contract; removing its record merely because it is old is
not an acceptable recovery procedure.

## One-time deployment configuration (separate approval required)

Nothing here authorizes applying this configuration to an operational server.
Normal PO testing uses the existing `start.bat` and never applies this overlay.

The optional `docker-compose.maintenance.yml` adds only a read-only public-proof
mount and independently pinned host/public-key identities. The private key and
backup archives must remain outside that directory. Do not mount the Docker
socket into the backend.

The Windows host companion is `scripts/server-maintenance/Windows-Host-Agent.ps1`.
Its mandatory parameters select the existing env file, exact Compose project,
local frontend URL and external HTTPS URL. It reads actual Compose labels,
container IDs, PostgreSQL storage mounts, cluster system identifier, database OID
and server startup time; it cross-checks the backend's actual runtime connection.
No server/container name is accepted as identity evidence by itself.

The runtime PostgreSQL address may use `inet::text` CIDR notation. The host
agent validates the numeric address and prefix and compares the exact host IP
against the PostgreSQL container's IPv4/IPv6 addresses. Matching a subnet alone
never proves identity. Invalid addresses fail closed; database name, OID and
PostgreSQL startup time must still independently match. The pure network tests
run on Windows without starting the operational agent or touching Docker.

Run the agent under the same Windows account that owns Docker Desktop. It stores
its RSA private key in that user's DPAPI-protected local data directory; the
folder ACL permits only that user and SYSTEM. The public key is UTF-8 PEM. Pin
its exact SHA256 and the reported hashed machine identity in the approved server
configuration using:

- `INHUIS_MAINTENANCE_PROOF_DIR`: agent's `Proof` directory only;
- `INHUIS_MAINTENANCE_PUBLIC_KEY_SHA256`: reported public-key digest;
- `INHUIS_MAINTENANCE_HOST_ID`: reported machine identity digest.

A substituted file/public key, different container, wrong machine or proof older
than 90 seconds is rejected. A cycle-specific backup proof is valid for at most
24 hours. Long maintenance beyond that requires a renewed verified backup proof.

The optional `-InstallAtLogon` switch registers a current-user interactive logon
task; this is an explicit deployment operation, not part of development or the
PO test. It uses the existing Docker Desktop login arrangement. It does not
change services, firewalls, restart policies or application startup scripts.

## Backup and physical storage proof

When the current maintenance cycle is draining and no durable operation remains,
the agent streams a full PostgreSQL custom archive as bytes into its protected
local directory. No password or row data is logged. It restores that archive
with `--exit-on-error` into a newly created isolated container using the already
running PostgreSQL image: no network, no ports, no production mounts, temporary
storage only. It compares every non-ephemeral domain table's count and sorted
row-content digest and owned sequence state with the live database, then checks live data again. The
archive is retained and SHA256-checked on every proof refresh.

Only the exact newly created restore container may be removed, after checking
its full ID, unique name and cycle label. Production containers and volumes are
never stopped, recreated, removed or reset. The agent does not run Compose up/down
or `start.bat`. A failed archive/probe is preserved for investigation; it is never
silently overwritten or advertised as a successful backup.

The signed before/after evidence includes Windows boot time, actual cluster and
volume identity, backend image, installed release/schema, and domain fingerprint.
Before/after evidence is retained with the canonical actor in the durable
maintenance audit, including after a subsequent maintenance cycle starts.
A changed network IP is allowed only when fresh independent physical identity
and data proof still match. A backend restart on the same Windows boot is not
sufficient. A copied/empty/different database cannot satisfy the data/identity
comparison merely by having the expected database name.

## Writer coverage and schema authority

Alembic creates the maintenance tables and PostgreSQL statement triggers for all
existing domain tables. The trigger locks the shared control row until the
writing transaction ends. Requests, workers and startup use durable operation
IDs, bound transaction-locally to the actual engine. Direct/unregistered database
writers cannot mutate domain tables after admission closes. Public receipt,
email/webhook and purchase-processing entrypoints also reserve before direct
CLI callers can perform file/network side effects.

Startup is registered before importing `app.main`; known legacy installer threads
must actually finish before that operation completes. Startup never reopens
admission. A missing/disabled barrier on any domain table stops startup, so a
future migration cannot silently add an unprotected table. New migrations must
extend the same barrier contract. Runtime code performs no schema creation.

Only session lifecycle and authentication audit, maintenance authority and the
Alembic revision table are infrastructure exceptions. No household, catalogue,
receipt, import, role or inventory table is exempt. The privileged historical
SQLite→PostgreSQL importer has an explicit transaction-local bypass only after
its existing immutable-source and fresh-target checks; normal requests cannot
invoke that importer. Backup restore is a separate isolated cluster.

## Development verification

The dedicated `Server maintenance isolated PostgreSQL validation` workflow uses
an expendable PostgreSQL database and random schemas. It covers admission races,
thread handoff, response background work, stale transitions, crash persistence,
DB rejection of unregistered writes, startup coverage, rollback refusal and
same/different database recovery. RSA signature tests cover key pinning, wrong
machine/container/cycle, expiry, backup/data mismatch and Windows-boot changes.
Windows CI parses the operational agent without executing server actions.
Full repository authorization, household, receipt/inventory, migration,
frontend/Playwright, version and exact-candidate gates remain required.

## Recovery login during maintenance

Authentication remains an infrastructure operation while domain admission is
closed. Login reads the persisted maintenance state under a shared transaction
lock before its optional Frontteam household synchronization. Synchronization
runs only in `normal` or `announced`; closed states use existing canonical
accounts, roles and memberships without provisioning domain data. Missing or
unknown maintenance authority fails closed. Password and session permissions
are unchanged, and no domain table is exempted from the write barrier.

The header retains the administrator's announcement throughout the maintenance
cycle. The standard blocking text is a fallback only when no message is present.
A running agent heartbeat is not proof that the post-reboot backup, identity,
data and route checks have passed. An expired cycle proof still blocks release.

## Windows restart: access while maintenance remains closed

After Windows and Docker start, the backend and frontend must be reachable even
when the persisted maintenance state is `draining`, `locked`, `verifying` or
`blocked`. A platform administrator with the existing recovery permission can
authenticate, inspect the maintenance evidence and use the existing controlled
completion action. No login or application startup automatically changes the
maintenance state or admits normal domain writes. Admission reopens only after
the administrator explicitly completes maintenance and all required checks pass.
