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
   Leave at least two minutes between announcement and involuntary session
   sign-out. A signed-in session is not evidence of current user activity.
   The administrator can explicitly choose **Resterende sessies beëindigen**,
   which requires **both** `platform.recovery.manage` and
   `platform.sessions.revoke`. A second confirmation is mandatory. All other
   unexpired sign-in sessions are revoked in one audited transaction; the
   administrator's own session remains valid. A client with unsaved form data
   may lose that unsaved input, so warn users beforehand. Session revocation
   blocks future authenticated requests but does **not** abort operations
   already admitted. A stale maintenance generation or a grace period shorter
   than two minutes fails closed. This action is allowed only in `announced`
   or `draining`, never as a shortcut around maintenance admission checks.
2. Select **Verwerkingen veilig stoppen**. A fresh, pinned Windows-agent heartbeat
   is required before this can close admission. Existing requests/worker handoffs
   finish; new domain requests and database writes are rejected. The screen polls
   and automatically attempts the final safety checks when operations reach zero.
   Winkelkoppelingen are not login sessions: their separate durable import
   admissions appear as **openstaande importregistraties**. An unfinished entry
   after a crash is not proof that an import is still actively running.
   The AH automatic scheduler checks maintenance admission before beginning a
   batch and between households. During draining it starts no further household
   imports; the currently admitted household finishes. On graceful app shutdown
   its stop request similarly prevents the next household from starting.
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
   After release, the running AH scheduler notices reopened admission within
   its short poll cycle and schedules due receipts again. On app/server startup
   the scheduler starts with its normal startup delay and reconciles known AH
   receipt IDs. This does not automatically replay a browser-assisted manual
   Jumbo/Lidl HTTP request interrupted by an abrupt host termination: that
   requires a separate durable work-queue/checkpoint design.

Errors, incomplete operations, missing/stale signatures and mismatched data
leave admission closed. There is no forced reboot, lease expiry or force-release.
An interrupted/crashed operation requires investigation and reconciliation using
its original domain contract; removing its record merely because it is old is
not an acceptable recovery procedure.

### Albert Heijn background sync: pre-import failure and historical operations

The AH scheduler retries due households every 15 minutes. A connection,
account-decoding or receipt-list error occurring **before** the first persisted
sync mutation and before downloading/importing any receipt is a demonstrably
pre-import failure. In that narrow case its background admission finishes
normally, while the scheduler still counts and reports a failed attempt. An
exception after the first persistence boundary, or an unknown interruption,
continues to leave the durable maintenance operation unresolved. No generic
crash-lease expiry or automatic cleanup is permitted.

On 26 October 2026 a read-only host report showed **38** unfinished operations,
all `call:_admitted_ah_sync`, generation 3, dated 24–26 October. The report
showed no other *active PostgreSQL work sessions at that instant*. It did not
prove whether any historical receipt imports had committed or whether external
network work was still running. Older records contain no durable per-operation
stage/outcome, so the new pre-import classification must **not** be inferred
retroactively from the operation kind, age, scheduler interval or zero sessions.

For those historical records, preserve the operation IDs and original rows;
first inspect the AH account's nonsecret sync metadata, canonical receipt-import
status, backend process lifetime and redacted failure classification. Compare
the evidence with the exact operation intervals and independently establish
which imports were committed, incomplete or never started. Reconciliation may
only be proposed for an explicitly verified set of IDs, with a recoverable
backup, audit record and separate platform-operator authorization. The actual
server reconciliation is **not** performed by this code change.

### Shortest safe interruption window

- Announce while normal usage continues; the two-minute notice period does
  **not** itself take the application offline.
- Near the planned time, optionally revoke remaining login sessions after the
  confirmation and then initiate the normal drain. Once draining, **new**
  domain work is denied, while previously admitted operations finish.
- Minimize actual downtime by initiating drain only when maintenance is ready;
  do not treat revoked sessions as evidence that operations are zero. A clean
  session list and an empty maintenance-operation list are distinct facts.
- If an operation is stuck, stay in a blocked state and reconcile the original
  workflow. Never terminate a backend, delete a maintenance-operation row,
  force-release or reboot based on session count alone.
- Windows forced power-off cannot be made graceful by application hooks. A
  crashed or interrupted receipt import requires source-idempotency checks and
  manual reconciliation of any unresolved durable admission. The historical
  38 AH admissions may be reconciled only after a verified independent backup,
  proof of receipt/source consistency and separately approved targeted cleanup.
- Proceed with the existing host-proof/backup gate, an operator-performed
  Windows reboot, exact image/data/route checks, and explicit release.
- The scanner path and the actual user-facing HTTP/HTTPS routes must be tested
  after each reboot; a green Docker container icon alone is not sufficient.
- A host agent which cannot establish the exact backend/physical PostgreSQL
  identity (including a stale scheduled task pointing to another Compose
  project) is **not** a valid source of restart permission.

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

The local frontend URL must target `localhost` or `127.0.0.1` on the **actual
user-facing published port**, not an assumed development port. The host agent
finds exactly one running container publishing that port and checks both its
Compose project and `frontend` service label, plus the actual `80/tcp` binding.
During installation and before a signed maintenance-cycle proof it also checks
that both the local and external HTTPS user routes render Inhuis and report the
same frontend release. During routine heartbeat it checks container/port identity
without making repeated external network requests. The backend's physical
PostgreSQL connection is checked separately; no same-Compose-project assumption
is made for the explicit split-database mode.

An existing or competing `Inhuis-Onderhoud-*` Windows Scheduled Task is **not**
overwritten, removed or silently disabled by `-InstallAtLogon`. If a stale task
points to another Compose project, installation stops with a clear diagnostic.
An operator must first reconcile the old task's identity and choose a separately
approved replacement procedure. This prevents two agents from publishing
conflicting maintenance evidence. A green browser login or Docker indicator is
not a substitute for that reconciliation.

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

## Windows-agent: sessiebestendigheid en veilige grens (30 oktober 2026)

De host-agent wordt onder het eigen Windows/Docker Desktop-account gestart. De
privésleutel gebruikt DPAPI CurrentUser; de geplande taak gebruikt daarom bewust
een interactieve **aanmeld**trigger. Dit is **geen** Windows-service die al bij
boot zonder aangemelde gebruiker kan functioneren. Een boot-trigger of SYSTEM-
account invoeren zonder bewezen DPAPI-sleuteloverdracht, Docker Desktop-toegang
en onafhankelijke integratietests is verboden. Een geslaagde heartbeat vóór
afmelden bewijst geen beschikbaarheid na afmelden of herstart.

Nieuwe installaties krijgen via de bestaande `-InstallAtLogon`-route een
onbegrensde taaklooptijd, drie herstartpogingen met een minuut interval,
inhaalstart bij gemiste aanmelding en geen automatische stop door accuwisseling.
Deze taakinstellingen wijzigen **geen bestaande taak automatisch**: die wordt
volgens het bestaande verbod op overschrijven eerst afzonderlijk beoordeeld.
Een eerder lokaal aangetoonde image-digest in `Config.Image` kan worden
geaccepteerd wanneer een onafhankelijke `docker image inspect` het exacte
lopende image-ID én een `postgres:17`-tag bevestigt. De bestaande fysieke
databasebinding en overige fail-closed controles blijven verplicht.

Voor een echte Windows-update/herstart van dezelfde Inhuis-versie:

1. Controleer eerst werkelijk actieve gebruikerssessies, importregistraties,
   de actuele backend/database-identiteit, de lokale/externe gebruikersroute,
   de AH-importstatus, de officiële agent en de mogelijkheid tot herstel.
2. Gebruik uitsluitend de bestaande platformbeheerdersroute om aan te kondigen,
   gecontroleerd te drainen en een ondertekende back-up/herstelproef te verkrijgen.
   Onopgeloste registraties blokkeren de herstart; wis ze niet op leeftijd.
3. Bevestig vóór reboot dat de **huidige images**, configuratie, data-identiteit
   en de normale `start.bat`-route veilig opnieuw te gebruiken zijn. De PO
   geeft afzonderlijk GO voor de daadwerkelijke Windows-herstart.
4. Na herstart moet eerst het Docker Desktop-account worden aangemeld en de
   officiële applicatie-opstartroute worden uitgevoerd/geverifieerd. Controleer
   de juiste brondata, versies, lokale/externe routes, scanner, agentstatus,
   verse handtekeningen en de verplichte onderhoudsproof.
5. Alleen een bevoegde platformbeheerder mag daarna expliciet onderhoud
   afronden. Bij ontbrekende bewijsvoering blijft de applicatie fail-closed.

Een **nieuwe Inhuis-versie uitrollen** is een aparte operatie met eigen
release-/deployment-GO en exact gecontroleerde kandidaat/image; dit document
geeft geen toestemming om productie te wijzigen. Tijdelijke codepatches in
lopende containers (zoals een tijdelijke importpauze) verdwijnen bij recreate
of upgrade. Een deployment is daarom geblokkeerd totdat de duurzame vervanging
(inclusief autorisatie, data, CI en migraties) geaccepteerd is.

Een test van alleen de actieve aanmeldsessie kan deze twee procedures niet als
volledig praktijkbewezen afronden. Herstart zonder aanmelding is expliciet
**niet ondersteund** door de huidige Docker Desktop/CurrentUser-architectuur.
