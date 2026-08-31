# Architectuur en datamodel

## Technische hoofdlijn

Rezzerv bestaat uit een React/Vite-frontend, FastAPI-backend, PostgreSQL 17, Docker Compose-runtime en GitHub Actions-gates.

Normale lokale runtime wordt gestart via `start.bat` en gebruikt gezamenlijk `docker-compose.yml`, `docker-compose.postgresql.yml` en Compose-profile `postgresql`.

Standaard lokale bindings:

- backend: `http://localhost:8011` naar containerpoort 8000;
- frontend: `http://localhost:5174` naar containerpoort 80;
- health: `http://localhost:8011/api/health`;
- PostgreSQL: `127.0.0.1:5432` naar containerpoort 5432.

PostgreSQL gebruikt de named volume `rezzerv_postgres`. Historische SQLite-bestanden zijn uitsluitend migratie-/rollbackartefacten en zijn geen actieve runtime-database.

## Database- en schema-authority

De PostgreSQL-credentials zijn operationeel gescheiden:

1. bootstrap-role - initialisatie van een verse PostgreSQL-cluster/database;
2. migrator-role - Alembic/schema-authority;
3. runtime-role - applicatie-DML, zonder schema-`CREATE`.

`MIGRATION_DATABASE_URL` gebruikt de migrator-role. `DATABASE_URL` gebruikt de runtime-role.

Alembic is de exclusieve schema-authority. Runtime/request-paden maken of wijzigen geen schema-objecten. Tijdens backend-start voert `app.runtime_preflight` de migratiepreflight met de migratorcredential uit en valideert daarna de runtimeverbinding tegen dezelfde schemahead.

De PostgreSQL-service geldt pas als operationeel gereed wanneer zowel migrator als runtime via TCP met hun eigen credentials kunnen authenticeren. Een bootstrap-only serverantwoord is daarvoor onvoldoende.

Zie `docs/project/POSTGRESQL-OPERATIONAL-STARTUP.md` voor de volledige operationele startupregels.

## Datalaag

De kernscheiding is:

1. **Global product** - centrale productkennis, identiteit en verrijking.
2. **Household article** - huishoudspecifieke representatie van een product.
3. **Inventory** - actuele voorraad binnen een huishouden.
4. **Inventory events** - aankopen, verbruik, correcties en verplaatsingen.
5. **Receipt/import** - bronregels die naar product en huishoudartikel worden gekoppeld.

Een centraal product mag nooit automatisch huishoudgegevens delen. Huishoudartikelen, locaties, voorraad en gebruik blijven per huishouden gescheiden.

## Identiteiten

Productidentiteiten omvatten onder meer GTIN/EAN/barcode, winkelartikelnummers, externe database-ID's en interne product-ID's. Normalisatie voorkomt duplicaten en ondersteunt koppeling.

## Migraties

Databasemigraties worden gefaseerd uitgevoerd. Per release geldt één hoofddoel met expliciete basisversie, doelversie, schemawijziging, backfill, compatibiliteit, herstelpad en regressietestscope.

Voor de SQLite → PostgreSQL-transitie geldt dat historische productie-SQLite niet als fictieve Alembic-revision wordt gestampt. Historische data wordt eerst tegen een verse canonical SQLite op de actuele Alembic-head geadopteerd/herbouwd en daarna naar een verse PostgreSQL-target geïmporteerd en strikt gevalideerd.
