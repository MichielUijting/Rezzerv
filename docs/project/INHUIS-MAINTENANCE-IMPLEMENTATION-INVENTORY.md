# Implementatie-inventarisatie onderhoudsmodus — PR #595

Status: eerste actuele code-inspectie (2026-10-21); **nog geen runtimewijziging**.

## Vastgesteld op `main`
- `backend/app/main.py` heeft circa 19.358 regels en fungeert als FastAPI-entrypoint; daarin zitten onder andere receipt-, voorraad- en productverwerkingen. Er is géén bevestigde route voor berichten/notifications aangetroffen in de gecontroleerde hoofdroutes. Dit bewijst NIET dat de berichtenmodule ontbreekt; die kan buiten `main.py` zitten.
- `frontend/nginx.conf` (eerder gecontroleerd) proxyt `/api/` naar de backend; een onderhoudsblokkering mag nooit alleen op frontend of reverse proxy steunen.
- `docs/security/ROLLEN-EN-ACCOUNTMODEL-v2.0.md` en `docs/security/AUTORISATIEMECHANISME-EN-MATRIX-v1.1.md` leggen platformrollen en server-side autorisatie vast. Gebruik een bestaande bevoegde platformrol; geef geen rechten aan iedereen met huishoudbeheer.
- `docs/project/ARCHITECTURE-AND-DATA.md`: PostgreSQL/Alembic zijn schema-autoriteit; runtime-schema-creatie is verboden.
- Actuele andere open PRs bij start: #594, #592, #570, #234. Onderhoudsontwikkeling mag de Jumbo-koppelingen in #594/#592 niet stilzwijgend overschrijven.

## Verplicht vóór aanpassing van muterende routes
1. Lokaliseer de **daadwerkelijke** berichtenmodule, inclusief API, database, ontvangerselectie en frontend (niet gokken op naam of alleen `main.py`).
2. Inventariseer **alle** muterende routes en writers in de actuele volledige codebase, inclusief hooks, scheduler, subprocessen, winkelkoppelingen, idempotente retries en werkers buiten de API.
3. Leg vast hoe processen start/commit/rollback doen, en hoe een durable admission/lease mechanisme zonder tussenvenster in PostgreSQL kan worden afgedwongen.
4. Controleer schema, Alembic-head, actieve productieversie en compatibiliteit van backend na restart.
5. Kies de kleinste coherente codewijziging. Een gedeeltelijk beveiligde onderhoudsknop mag **niet** als gereed of veilig voor herstart worden aangeboden.

## Ontwikkelvolgorde
A. Gedeelde onderhoudsstatus en audit, migratie en specifieke service met atomair admission-protocol.
B. Doorvoering in alle muterende request- en achtergrondpaden (zonder cross-household bypass).
C. Bestaande berichtenmodule gebruiken voor aankondiging/start/einde.
D. Beheerbediening met blokkerend groen-criterium; fail-closed herstel na herstart.
E. Concurrency-, crash-, retry- en data-integriteitstests in geïsoleerde PostgreSQL-omgeving.
F. Definitieve patchversionering, CI/preflight, exacte SHA-regressie, functionele PO-test; pas daarna Ready.

## Stopregel
Geen schema-/Docker-/volume-/Windows-/productiewijzigingen op de applicatieserver vanuit deze PR. Geen Ready en geen merge zolang A–F ontbreken. Tijdelijk onderhoud blijft begeleid en handmatig aangekondigd; geen garantie dat alleen afwezigheid van ingelogde gebruikers een veilige herstart bewijst.
