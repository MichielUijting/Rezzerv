# Rezzerv main-consolidatie — manifest v1

## Doel

Een schone, controleerbare productbaseline opbouwen vanaf `main`, zonder historische back-ups, diagnose-uitvoer, tijdelijke patchscripts of lokale OCR-artefacten mee te nemen.

## Bronnen

- uitgangspunt: `main`;
- functionele referentie: `fix/m2c2i-2a-kassa-duplicate-overlay`;
- benodigde productlijn: Kassa, Uitpakken en Externe databases.

## Overnemen uit de PO-referentie

### Externe databases — backend

- `backend/app/services/external_database_matchers.py`
- `backend/app/services/external_product_candidate_store.py`
- `backend/app/services/external_product_catalog_store.py`
- `backend/app/services/external_product_index_store.py`
- `backend/app/services/external_relation_batch_store.py`

### Externe databases — frontend

- `frontend/src/features/externalDatabases/ExternalDatabasesPage.jsx`
- `frontend/src/features/externalDatabases/ReceiptItemsOverview.jsx`
- `frontend/src/features/externalDatabases/externalDatabases.css`

### Verplichte integratiepunten

- `backend/app/api/system_routes.py`
- `frontend/src/app/router/AppRouter.jsx`
- `frontend/src/features/home/HomePage.jsx`

## Behouden uit main

- Uitpakken: locatiepicker, bulk-toekenning, artikelbenaming, kolomvolgorde en exportlocatie.
- bestaande actieve routes, runtimeconfiguratie en productfunctionaliteit die niet door de PO-referentie wordt vervangen.

## Niet opnemen

- `*.bak`, `*_backup_*`, `*.R*_backup_*`;
- `apply-*.ps1`, tijdelijke patchscripts en historische herstelhulpen;
- `backend/data/receipts/debug/**`, `tools/debug_output/**`, lokale runtime-statusbestanden;
- tijdelijke OCR-afbeeldingen, diagnose-JSON, analyse-uitvoer en response-dumps;
- tijdelijke M2C2f-notities, markers, status- en merge-notities.

## Kassa

De actieve router importeert `frontend/src/features/kassa/KassaPage.jsx`. Dit bestand is een wrapper naar `frontend/src/features/receipts/KassaPage.jsx`; de laatste is daarom de canonieke Kassa-implementatie.

## Verplichte validatie vóór merge naar main

1. Frontend build.
2. Backend syntax/importcontrole.
3. Kassa-regressie voor AH, Aldi, Jumbo, Plus, Picnic en Lidl.
4. Uitpakken smoke en regressie.
5. Externe databases: retailerisolatie, Lidl-taxonomiepreview, kandidaatopslag en geen automatische catalogus-/huishoud-/voorraadmutatie.
6. Handmatige PO-test van Kassa, Uitpakken en Externe databases.

## Besluitregel

Er wordt geen directe merge van de historische PO-branch naar `main` uitgevoerd. Alleen geselecteerde productcode en gecontroleerde integratiepunten worden in deze consolidatielijn opgenomen.
