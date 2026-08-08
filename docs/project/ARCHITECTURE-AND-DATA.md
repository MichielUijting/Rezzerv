# Architectuur en datamodel

## Technische hoofdlijn

Rezzerv bestaat uit een React/Vite-frontend, FastAPI-backend, relationele database, Docker Compose-runtime en GitHub Actions-gates.

Lokale runtime:

- backend: `http://localhost:8011` naar containerpoort 8000;
- frontend: `http://localhost:5174` naar containerpoort 80;
- health: `http://localhost:8011/api/health`.

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
