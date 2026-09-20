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

**Catalogus en Externe databases zijn platformbrede domeinen.** De definitieve koppeling tussen een winkel-/bonartikel en een centraal product wordt centraal opgeslagen en geprojecteerd. `household_articles.global_product_id` blijft een huishoudspecifieke relatie en mag niet als fallback of blokkade voor een platformbrede Cataloguskoppeling worden gebruikt. Een platformbrede externe-databaseactie mag daarom niet stilzwijgend household articles, bonregels of purchase-importregels van één huishouden wijzigen.

## Identiteiten

Productidentiteiten omvatten onder meer GTIN/EAN/barcode, winkelartikelnummers, externe database-ID's en interne product-ID's. Normalisatie voorkomt duplicaten en ondersteunt koppeling.

Een centrale winkel-/bonartikelkoppeling kent twee expliciete identiteitsmodi:

1. **exact** — het centrale product heeft een geldige primaire GTIN/EAN, een bijpassende GTIN-identiteit en een actieve officiële GS1 GPC-classificatie;
2. **generic** — het centrale product is expliciet gemarkeerd met bron `external_databases_generic`, heeft geen GTIN, merk of variant nodig en heeft wél een actieve officiële GS1 GPC-classificatie. De bevestigde bonartikelkoppeling wordt daarbij gemarkeerd met `confirmed_by=external_databases_generic_link`.

De generieke modus is geen fallback op een incompleet exact product. Alleen een bewuste generieke gebruikersactie mag een GTIN-loos product als geldige centrale bonartikelkoppeling bevestigen. Andere incomplete Catalogusproducten blijven fail-closed.

Een expliciete huismerkmarker in de bontekst is onderdeel van de **exacte** identiteitsbewaking: bij een herkenbare marker van de winkelketen (zoals `AH` bij Albert Heijn) moet een exact extern product een passende merkidentiteit aantonen. Een conflict wordt voor exacte koppelingen in automatische kandidaatselectie, write-route en read-projectie fail-closed behandeld. Handmatig zoeken mag conflicterende producten wel als niet-koppelbare zoekresultaten tonen. Een expliciet generieke koppeling valt niet onder deze exacte merkregel, omdat zij bewust geen merkidentiteit claimt.

## Migraties

Databasemigraties worden gefaseerd uitgevoerd. Per release geldt één hoofddoel met expliciete basisversie, doelversie, schemawijziging, backfill, compatibiliteit, herstelpad en regressietestscope.

Voor de SQLite → PostgreSQL-transitie geldt dat historische productie-SQLite niet als fictieve Alembic-revision wordt gestampt. Historische data wordt eerst tegen een verse canonical SQLite op de actuele Alembic-head geadopteerd/herbouwd en daarna naar een verse PostgreSQL-target geïmporteerd en strikt gevalideerd.
