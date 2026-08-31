# PostgreSQL operationele startup

## Doel en status

Dit document legt de operationele runtime-regels vast voor de PostgreSQL-runtime van Rezzerv/Inhouse.

Het vertaalt de blijvende startup- en databaseconsistentieprincipes uit het historische Release Protocol en de Release Gate naar de PostgreSQL-architectuur. Letterlijke SQLite-pad-, SQLite-bestands- en file-mountregels uit die oudere documenten zijn voor de actieve runtime niet meer leidend.

De kernregel blijft ongewijzigd: **binnen één actieve omgeving bestaat exact één aangewezen runtime-database en de actieve database moet aantoonbaar zijn.**

## Normale opstartroute

Voor normaal PO-gebruik is `start.bat` de enige aangewezen lokale opstartroute.

`start.bat` gebruikt gezamenlijk:

- `docker-compose.yml`;
- `docker-compose.postgresql.yml`;
- Compose-profile `postgresql`.

Losse PowerShell-, Python-, backend- of frontendstarts zijn diagnose-/ontwikkelroutes en zijn geen vervanging voor de normale operationele startup.

## Lokale runtime

Standaard hostbindings:

- frontend: `http://localhost:5174` → containerpoort 80;
- backend: `http://localhost:8011` → containerpoort 8000;
- backend health: `http://localhost:8011/api/health`;
- PostgreSQL: `127.0.0.1:5432` → containerpoort 5432.

Voor geïsoleerde technische rehearsals mogen hostpoorten via de daarvoor bedoelde `REZZERV_*_PORT`-variabelen worden overschreven. PostgreSQL blijft loopback-only gepubliceerd.

## PostgreSQL runtime authority

De actieve relationele runtime is PostgreSQL 17.

De persistentie gebruikt de Compose named volume `rezzerv_postgres`. Historische SQLite-bestanden zijn uitsluitend bron-, migratie- of rollbackartefacten en mogen niet als actieve runtime-database worden aangekoppeld.

De backendhealth moet fail-closed aantonen:

- `status == ok`;
- `datastore == postgresql`;
- een niet-lege PostgreSQL database-identiteit.

Een SQLite-pad zoals `/app/data/rezzerv.db` is geen geldige runtime-identiteit meer.

## Rollen en schema-authority

De PostgreSQL-rollen zijn gescheiden:

- bootstrap-role: alleen initialisatie van de verse PostgreSQL-cluster/database;
- migrator-role: Alembic/schema-authority;
- runtime-role: applicatie-DML zonder schema-`CREATE`.

`MIGRATION_DATABASE_URL` gebruikt de migrator-role. `DATABASE_URL` gebruikt de runtime-role. Deze credentials mogen niet samenvallen.

Alembic is de exclusieve schema-authority. Productieruntimecode en request-paden maken of wijzigen geen schema-objecten.

## Readiness

`postgres` mag pas `Healthy` worden wanneer de split-role-initialisatie werkelijk bruikbaar is.

Daarom is een bootstrap-only `pg_isready`-antwoord onvoldoende. De operationele healthcheck bewijst via TCP op `127.0.0.1` dat zowel de migrator-role als de runtime-role met hun eigen credentials kunnen authenticeren.

Hierdoor kan de backend niet starten tegen de tijdelijke initialisatieserver van de officiële PostgreSQL-image voordat `/docker-entrypoint-initdb.d` volledig is afgerond.

## Wat `start.bat` moet bewaken

De normale startup bewaakt in deze volgorde de blijvende historische invarianten:

1. geldige projectroot en vereiste projectbestanden;
2. beschikbare Docker-engine;
3. lokale runtime-/buildartefacten veilig opschonen;
4. geldig samengevoegd Compose-model met de PostgreSQL-service;
5. gecontroleerde legacy-/poortcleanup;
6. imagebuild;
7. PostgreSQL/backend/frontend starten;
8. wachten op role-ready PostgreSQL en backend-health;
9. actieve datastore/database-identiteit als PostgreSQL verifiëren;
10. frontendbereikbaarheid en exacte frontendversie verifiëren;
11. pas daarna de frontend voor normaal gebruik openen.

## Stopregels

Startup/release blijft geblokkeerd wanneer één van de volgende situaties bestaat:

- PostgreSQL-service ontbreekt uit het actieve Compose-model;
- PostgreSQL is niet role-ready;
- migrator/runtime-credentials zijn niet gescheiden;
- runtime-role bezit schema-`CREATE`;
- Alembic/schemahead is niet geldig;
- `/api/health` meldt niet `postgresql`;
- een SQLite-bestand of alternatieve database fungeert als runtime;
- niet aantoonbaar is welke database de geteste backend gebruikt;
- frontendversie en repositoryversie verschillen.

## Productie-cutover

Deze operationele startupbaseline voert op zichzelf geen productie-datacutover uit.

Een productie-cutover vereist afzonderlijk de bewezen route: immutable SQLite-snapshot → canonical SQLite adoption/rebuild → verse PostgreSQL-target op canonical Alembic-head → importer/equivalentie → runtime- en frontendvalidatie. De historische SQLite-snapshot blijft daarbij read-only rollbackbewijs.
