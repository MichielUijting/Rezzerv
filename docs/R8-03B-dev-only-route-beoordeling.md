# R8-03B — Beoordeling resterende DEV_ONLY-routes

Status: uitgevoerd als governance-beoordeling
Scope: classificatie en besluitvoorbereiding
Runtime-impact: geen
Database-impact: geen
Parser/OCR-impact: geen

## Aanleiding

Na R8-03A zijn de vijf hoogste-risico dev-routes verwijderd uit de runtime. Het actuele route-governance manifest toont nog 35 routes met classificatie `DEV_ONLY`.

Deze stap beoordeelt deze resterende routes op functionele waarde, risico en gewenste vervolgbestemming.

## Besluitcategorieën

| Besluit | Betekenis |
|---|---|
| HOUDEN_DEV | Mag voorlopig als ontwikkelroute blijven bestaan |
| VERPLAATS_NAAR_TEST | Hoort functioneel bij regressie/testdiagnostiek en moet later onder `/api/testing/*` komen |
| VERPLAATS_NAAR_ADMIN | Is een beheermutatie en hoort later onder `/api/admin/*` met duidelijke beheercontext |
| VERWIJDERKANDIDAAT | Waarschijnlijk verwijderen na referentiecheck |

## Beoordeling resterende DEV_ONLY-routes

| Route | Huidige functie | Beoordeling | Reden |
|---|---|---|---|
| `/api/dev/article-history` | Artikelhistorie inspecteren | VERPLAATS_NAAR_TEST | Diagnose/read-only, geen normale productieroute |
| `/api/dev/articles/archive` | Artikel archiveren via dev-route | VERWIJDERKANDIDAAT | Dubbeling met reguliere artikel-archive routes |
| `/api/dev/articles/{article_id}/automation-override` | Dev-mutatie artikelautomatisering | VERWIJDERKANDIDAAT | Dubbeling met reguliere automation override routes |
| `/api/dev/browser-regression/reset-fixture` | Browserregressiefixture resetten | VERPLAATS_NAAR_TEST | Testfixture, niet gewone runtime |
| `/api/dev/diagnostics/store-location-options` | Winkel/locatie diagnose | VERPLAATS_NAAR_TEST | Diagnosefunctie |
| `/api/dev/diagnostics/store-process-validation` | Winkelprocesvalidatie | VERPLAATS_NAAR_TEST | Diagnosefunctie |
| `/api/dev/export-receipt-export-fixture` | Fixture-export voor receipt tests | VERPLAATS_NAAR_TEST | Testartefact |
| `/api/dev/generate-article-testdata` | Artikeltestdata genereren | VERWIJDERKANDIDAAT | Testdatagenerator vervuilt runtime |
| `/api/dev/generate-layer1-receipt-fixture` | Receipt layer-1 fixture genereren | VERPLAATS_NAAR_TEST | Regressietesthulpmiddel |
| `/api/dev/generate-receipt-export-fixture` | Receipt export fixture genereren | VERPLAATS_NAAR_TEST | Regressietesthulpmiddel |
| `/api/dev/household/almost-out-settings` | Dev-mutatie almost-out instellingen | VERWIJDERKANDIDAAT | Dubbeling met reguliere household-route |
| `/api/dev/household/automation-settings` | Dev-mutatie automatiseringsinstellingen | VERWIJDERKANDIDAAT | Dubbeling met reguliere household-route |
| `/api/dev/household/store-import-settings` | Dev-mutatie winkelimportinstellingen | VERWIJDERKANDIDAAT | Dubbeling met reguliere household-route |
| `/api/dev/inventory` | Dev-voorraadmutatie | VERWIJDERKANDIDAAT | Dubbeling met productievoorraadflow en risicovol |
| `/api/dev/inventory-preview` | Voorraadpreview | VERPLAATS_NAAR_TEST | Diagnose/read-only |
| `/api/dev/inventory/{inventory_id}` | Dev-voorraadupdate | VERWIJDERKANDIDAAT | Dubbeling met normale voorraadmutaties |
| `/api/dev/purchase-import-batches/{batch_id}/diagnostics` | Importbatchdiagnose | VERPLAATS_NAAR_TEST | Diagnosefunctie |
| `/api/dev/regression/almost-out-prediction` | Regressietest almost-out voorspelling | VERPLAATS_NAAR_TEST | Testfunctie |
| `/api/dev/regression/almost-out-self-test` | Backend self-test almost-out | VERPLAATS_NAAR_TEST | Testfunctie |
| `/api/dev/regression/ensure-inventory-fixture` | Regressiefixture aanmaken | VERPLAATS_NAAR_TEST | Testfixture, niet productie |
| `/api/dev/regression/receipt-fixture-file` | Receipt fixturebestand ophalen | VERPLAATS_NAAR_TEST | Testartefact |
| `/api/dev/regression/seed-kassa-receipts` | Kassabonregressiedata seeden | VERPLAATS_NAAR_TEST | Testdata, mogelijk later alleen lokaal toegestaan |
| `/api/dev/run-layer1-tests` | Layer-1 tests draaien | VERPLAATS_NAAR_TEST | Test-runner |
| `/api/dev/run-layer2-tests` | Layer-2 tests draaien | VERPLAATS_NAAR_TEST | Test-runner |
| `/api/dev/run-layer3-tests` | Layer-3 tests draaien | VERPLAATS_NAAR_TEST | Test-runner |
| `/api/dev/run-parsing-fixture-tests` | Parsing fixture tests draaien | VERPLAATS_NAAR_TEST | Test-runner |
| `/api/dev/run-parsing-raw-tests` | Raw parsing tests draaien | VERPLAATS_NAAR_TEST | Test-runner |
| `/api/dev/run-regression-tests` | Regressietests draaien | VERPLAATS_NAAR_TEST | Test-runner |
| `/api/dev/run-smoke-tests` | Smoke tests draaien | VERPLAATS_NAAR_TEST | Test-runner |
| `/api/dev/spaces` | Dev-route ruimte aanmaken | VERWIJDERKANDIDAAT | Dubbeling met reguliere `/api/spaces` |
| `/api/dev/status` | Dev-status tonen | HOUDEN_DEV | Laag risico; nuttig als ontwikkelstatus zolang dev-routes bestaan |
| `/api/dev/sublocations` | Dev-route sublocatie aanmaken | VERWIJDERKANDIDAAT | Dubbeling met reguliere `/api/sublocations` |
| `/api/dev/test-report` | Testrapport voltooien | VERPLAATS_NAAR_TEST | Testadministratie |
| `/api/dev/test-report/latest` | Laatste testrapport ophalen | VERPLAATS_NAAR_TEST | Testadministratie |
| `/api/dev/test-status` | Teststatus ophalen | VERPLAATS_NAAR_TEST | Testadministratie |

## Samenvatting

| Besluit | Aantal |
|---|---:|
| HOUDEN_DEV | 1 |
| VERPLAATS_NAAR_TEST | 24 |
| VERPLAATS_NAAR_ADMIN | 0 |
| VERWIJDERKANDIDAAT | 10 |

## Verwijderkandidaten

Deze routes lijken functioneel overbodig omdat er reguliere productie- of adminroutes voor bestaan:

```text
/api/dev/articles/archive
/api/dev/articles/{article_id}/automation-override
/api/dev/generate-article-testdata
/api/dev/household/almost-out-settings
/api/dev/household/automation-settings
/api/dev/household/store-import-settings
/api/dev/inventory
/api/dev/inventory/{inventory_id}
/api/dev/spaces
/api/dev/sublocations
```

## Routes die naar TEST horen

De meeste resterende `DEV_ONLY`-routes zijn eigenlijk test- of diagnoseroutes. Deze moeten niet per se verwijderd worden, maar wel uit `/api/dev/*` verdwijnen en later onder een expliciete testnamespace komen:

```text
/api/testing/regression/*
/api/testing/diagnostics/*
/api/testing/fixtures/*
/api/testing/reports/*
```

## Aanbevolen vervolgstap

R8-03C — verwijder eerst de 10 duidelijke dubbelingen/verwijderkandidaten.

Daarna R8-04 — migreer de 24 nuttige test- en diagnoseroutes van `/api/dev/*` naar `/api/testing/*`, of verberg ze achter een expliciete testmodus.

## Stopregel

Geen route verwijderen zonder voorafgaande referentiecheck op:

1. frontend-aanroepen;
2. scripts;
3. regressietooling;
4. tests;
5. documentatie;
6. Swagger/runtime-manifest na rebuild.
