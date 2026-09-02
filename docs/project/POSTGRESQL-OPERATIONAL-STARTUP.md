# PostgreSQL operationele startup

## Doel en status

Dit document legt de operationele runtime-regels vast voor de PostgreSQL-runtime van Rezzerv/Inhouse.

Het vertaalt de blijvende startup- en databaseconsistentieprincipes uit het historische Release Protocol en de Release Gate naar de PostgreSQL-architectuur. Letterlijke SQLite-pad-, SQLite-bestands- en file-mountregels uit die oudere documenten zijn voor de actieve runtime niet meer leidend.

De kernregel blijft ongewijzigd: **binnen één actieve omgeving bestaat exact één aangewezen runtime-database en de actieve database moet aantoonbaar zijn.**

Actuele bewezen baseline per 2 september 2026:

- productversie: `Rezzerv-MVP-v01.12.109`;
- runtime: PostgreSQL 17;
- canonical Alembic-head: `20260902_01`;
- operationele startup en volledige PostgreSQL-ketentest zijn afzonderlijke bewijsroutes.

## Normale opstartroute

Voor normaal PO-gebruik is `start.bat` de enige aangewezen lokale opstartroute.

`start.bat` gebruikt gezamenlijk:

- `docker-compose.yml`;
- `docker-compose.postgresql.yml`;
- Compose-profile `postgresql`.

Losse PowerShell-, Python-, backend- of frontendstarts zijn diagnose-/ontwikkelroutes en zijn geen vervanging voor de normale operationele startup.

`start.bat` voert één volledige stackstart uit via Compose. Er volgt geen tweede geforceerde frontend-recreate nadat de stack al is gestart. Na de imagebuild en stackstart controleert de routine readiness, backend-health, datastore-identiteit en frontendversie voordat de startup als geslaagd geldt.

## Lokale runtime

Standaard hostbindings:

- frontend: `http://localhost:5174` → containerpoort 80;
- backend: `http://localhost:8011` → containerpoort 8000;
- backend health: `http://localhost:8011/api/health`;
- PostgreSQL: `127.0.0.1:5432` → containerpoort 5432.

Voor geïsoleerde technische rehearsals mogen hostpoorten via de daarvoor bedoelde `REZZERV_*_PORT`-variabelen worden overschreven. PostgreSQL blijft op de host loopback-only gepubliceerd.

De hostbinding `127.0.0.1:5432` is niet hetzelfde als de interne readinessroute. Backend en PostgreSQL-healthcheck gebruiken binnen het Compose-netwerk de servicenaam `postgres` en poort 5432.

## PostgreSQL runtime authority

De actieve relationele runtime is PostgreSQL 17.

De persistentie gebruikt de Compose named volume `rezzerv_postgres`. Historische SQLite-bestanden zijn uitsluitend bron-, migratie- of rollbackartefacten en mogen niet als actieve runtime-database worden aangekoppeld.

De normale startup mag de named volume `rezzerv_postgres` niet verwijderen. Een normale stop/start- of startupcleanup gebruikt daarom geen `docker compose down -v` voor de operationele stack.

De backendhealth moet fail-closed aantonen:

- `status == ok`;
- `datastore == postgresql`;
- een niet-lege PostgreSQL database-identiteit.

Een SQLite-pad zoals `/app/data/rezzerv.db` is geen geldige runtime-identiteit meer.

## Rollen en schema-authority

De PostgreSQL-rollen zijn gescheiden:

- bootstrap-role: alleen initialisatie van de verse PostgreSQL-cluster/database;
- migrator-role `rezzerv_migrator`: Alembic/schema-authority;
- runtime-role `rezzerv_app`: applicatie-DML zonder schema-`CREATE`.

`MIGRATION_DATABASE_URL` gebruikt de migrator-role. `DATABASE_URL` gebruikt de runtime-role. Deze credentials mogen niet samenvallen.

Alembic is de exclusieve schema-authority. Productieruntimecode en request-paden maken of wijzigen geen schema-objecten.

De migration credential is alleen beschikbaar waar schema-preflight/migratie die nodig heeft. De normale business-runtime en de officiële ketentest bewijzen dat de migratiecredential tijdens de productieketen afwezig is.

## Readiness en credential-drift

`postgres` mag pas `Healthy` worden wanneer de split-role-initialisatie werkelijk bruikbaar is.

Daarom is een bootstrap-only `pg_isready`-antwoord onvoldoende. De operationele healthcheck bewijst via TCP over de **Compose-netwerkroute `postgres:5432`** dat zowel de migrator-role als de runtime-role met hun eigen credentials kunnen authenticeren.

Deze route is bewust dezelfde netwerkgrens die de backend gebruikt. Een healthcheck die uitsluitend via `127.0.0.1` in de PostgreSQL-container authenticeert is onvoldoende als operationeel bewijs, omdat daarmee credential-drift in een reeds bestaande persistent volume gemist kan worden.

Wanneer de in Compose/.env aangeboden rolecredentials niet overeenkomen met de opgeslagen PostgreSQL-roleverifiers in de bestaande volume, moet PostgreSQL daarom niet `Healthy` worden en mag de backend niet als operationeel gestart worden beschouwd. Credential-drift wordt eerst expliciet hersteld; de volume of productiedata wordt daarvoor niet gewist.

## Wat `start.bat` moet bewaken

De normale startup bewaakt in deze volgorde de blijvende historische invarianten:

1. geldige projectroot en vereiste projectbestanden;
2. beschikbare Docker-engine;
3. lokale runtime-/buildartefacten veilig opschonen;
4. geldig samengevoegd Compose-model met de PostgreSQL-service;
5. gecontroleerde legacy-/poortcleanup;
6. imagebuild;
7. PostgreSQL/backend/frontend één keer als volledige stack starten;
8. wachten op role-ready PostgreSQL via `postgres:5432` en backend-health;
9. actieve datastore/database-identiteit als PostgreSQL verifiëren;
10. frontendbereikbaarheid en exacte frontendversie verifiëren;
11. pas daarna de frontend voor normaal gebruik openen en `Startup complete.` melden.

Een operationeel groen bewijs bevat minimaal:

- PostgreSQL-service `Healthy`;
- backend gestart;
- `/api/health` met `status: ok`, `datastore: postgresql` en database `rezzerv`;
- frontend HTTP-bereikbaar op poort 5174;
- `start.bat` eindigt zelfstandig met `Startup complete.`.

## Startup is geen volledige ketentest

Een succesvolle `start.bat` bewijst de operationele stack en bereikbaarheid, maar bewijst **niet** de volledige Kassabon → Voorraad → Bijna-op-businessketen.

De canonical volledige ketentest is:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-receipt-inventory-chain.ps1
```

Deze runner gebruikt een geïsoleerd Compose-project `rezzerv-receipt-chain-test` en een eigen PostgreSQL-testvolume. De operationele `rezzerv_postgres`-volume wordt niet gebruikt als ketentestdatabase en niet verwijderd.

De keten is pas technisch groen bij **12/12 stappen**, inclusief PostgreSQL, DML-only runtime, afwezige migratiecredential tijdens de businessketen, idempotentie, product/producttypekoppeling, loyalty-exclusie, voorraadpad `0 -> 2 -> 5 -> 5 -> 1`, Bijna-op-pad `NEE -> JA`, succesvolle geïsoleerde cleanup en exitcode `0`.

Zie `docs/project/DEVELOPMENT-TEST-RELEASE.md` en `docs/Rezzerv-procesketen-kassa-voorraad-bijna-op.md`.

## Stopregels

Startup/release blijft geblokkeerd wanneer één van de volgende situaties bestaat:

- PostgreSQL-service ontbreekt uit het actieve Compose-model;
- PostgreSQL is niet role-ready via de Compose-netwerkroute;
- migrator/runtime-credentials zijn niet gescheiden;
- opgeslagen PostgreSQL-rolecredentials en actuele Composecredentials driften;
- runtime-role bezit schema-`CREATE`;
- Alembic/schemahead is niet geldig;
- `/api/health` meldt niet `postgresql`;
- een SQLite-bestand of alternatieve database fungeert als runtime;
- niet aantoonbaar is welke database de geteste backend gebruikt;
- frontendversie en repositoryversie verschillen.

## Productie-cutover

Deze operationele startupbaseline voert op zichzelf geen productie-datacutover uit.

Een productie-cutover vereist afzonderlijk de bewezen route: immutable SQLite-snapshot → canonical SQLite adoption/rebuild → verse PostgreSQL-target op canonical Alembic-head → importer/equivalentie → runtime- en frontendvalidatie. De historische SQLite-snapshot blijft daarbij read-only rollbackbewijs.
