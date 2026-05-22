# R8-04A — Migratieplan DEV_ONLY → TEST

Status: uitgevoerd als migratieplan
Scope: resterende 25 `/api/dev/*` routes
Runtime-impact: geen
Database-impact: geen
Parser/OCR-impact: geen

## Aanleiding

Na R8-03C toont het route-governance manifest:

| Klasse | Aantal |
|---|---:|
| ADMIN | 6 |
| DEV_ONLY | 25 |
| LEGACY | 10 |
| PROD | 104 |
| TEST | 8 |

De high-risk dev-routes zijn verwijderd. De resterende `DEV_ONLY` routes zijn vooral regressie-, diagnose-, fixture- en testroutes. Functioneel zijn veel daarvan nuttig, maar de namespace `/api/dev/*` is onduidelijk voor een beheerbare MVP-runtime.

Doel van R8-04 is om nuttige testfunctionaliteit expliciet onder `/api/testing/*` te plaatsen en `/api/dev/*` verder uit te faseren.

## Migratieprincipes

1. Geen parser-, OCR- of kassabonlogica wijzigen.
2. Geen database wissen of migreren.
3. Eerst aliases toevoegen onder `/api/testing/*`.
4. Daarna frontend/scripts omzetten naar de nieuwe paden.
5. Pas daarna oude `/api/dev/*` aliases verwijderen.
6. High-risk routes blijven verwijderd en keren niet terug.

## Nieuwe naamgevingsstructuur

| Oude soort | Nieuwe namespace |
|---|---|
| Regressierunners | `/api/testing/regression/*` |
| Diagnoses | `/api/testing/diagnostics/*` |
| Fixtures | `/api/testing/fixtures/*` |
| Testrapportage | `/api/testing/reports/*` |
| Teststatus | `/api/testing/status` |
| Algemene dev-status | verwijderen of admin-diagnose maken |

## Route-migratietabel

| Oude route | Nieuwe route | Type | Backward compatibility | Besluit |
|---|---|---|---|---|
| `/api/dev/article-history` | `/api/testing/diagnostics/article-history` | diagnose | tijdelijk alias | migreren |
| `/api/dev/browser-regression/reset-fixture` | `/api/testing/fixtures/browser-regression/reset` | fixture | tijdelijk alias | migreren |
| `/api/dev/diagnostics/store-location-options` | `/api/testing/diagnostics/store-location-options` | diagnose | tijdelijk alias | migreren |
| `/api/dev/diagnostics/store-process-validation` | `/api/testing/diagnostics/store-process-validation` | diagnose | tijdelijk alias | migreren |
| `/api/dev/export-receipt-export-fixture` | `/api/testing/fixtures/receipt-export/download` | fixture export | tijdelijk alias | migreren |
| `/api/dev/generate-layer1-receipt-fixture` | `/api/testing/fixtures/receipt-layer1/generate` | fixture generator | tijdelijk alias | migreren |
| `/api/dev/generate-receipt-export-fixture` | `/api/testing/fixtures/receipt-export/generate` | fixture generator | tijdelijk alias | migreren |
| `/api/dev/inventory-preview` | `/api/testing/diagnostics/inventory-preview` | diagnose | tijdelijk alias | migreren |
| `/api/dev/purchase-import-batches/{batch_id}/diagnostics` | `/api/testing/diagnostics/purchase-import-batches/{batch_id}` | diagnose | tijdelijk alias | migreren |
| `/api/dev/regression/almost-out-prediction` | `/api/testing/regression/almost-out-prediction` | regressie | tijdelijk alias | migreren |
| `/api/dev/regression/almost-out-self-test` | `/api/testing/regression/almost-out-self-test` | regressie | tijdelijk alias | migreren |
| `/api/dev/regression/ensure-inventory-fixture` | `/api/testing/fixtures/inventory/ensure` | fixture | tijdelijk alias | migreren |
| `/api/dev/regression/receipt-fixture-file` | `/api/testing/fixtures/receipt/file` | fixture | tijdelijk alias | migreren |
| `/api/dev/regression/seed-kassa-receipts` | `/api/testing/fixtures/receipts/seed-kassa` | fixture seed | tijdelijk alias | migreren, later mogelijk lokaal-only |
| `/api/dev/run-layer1-tests` | `/api/testing/regression/layer1/run` | testrunner | tijdelijk alias | migreren |
| `/api/dev/run-layer2-tests` | `/api/testing/regression/layer2/run` | testrunner | tijdelijk alias | migreren |
| `/api/dev/run-layer3-tests` | `/api/testing/regression/layer3/run` | testrunner | tijdelijk alias | migreren |
| `/api/dev/run-parsing-fixture-tests` | `/api/testing/regression/parsing-fixtures/run` | testrunner | tijdelijk alias | migreren |
| `/api/dev/run-parsing-raw-tests` | `/api/testing/regression/parsing-raw/run` | testrunner | tijdelijk alias | migreren |
| `/api/dev/run-regression-tests` | `/api/testing/regression/all/run` | testrunner | tijdelijk alias | migreren |
| `/api/dev/run-smoke-tests` | `/api/testing/regression/smoke/run` | testrunner | tijdelijk alias | migreren |
| `/api/dev/status` | `/api/testing/status` | status | tijdelijk alias | migreren of verwijderen |
| `/api/dev/test-report` | `/api/testing/reports/complete` | testrapport | tijdelijk alias | migreren |
| `/api/dev/test-report/latest` | `/api/testing/reports/latest` | testrapport | tijdelijk alias | migreren |
| `/api/dev/test-status` | `/api/testing/status` | status | tijdelijk alias | migreren |

## Aanpak in releases

### R8-04B — Nieuwe TEST aliases toevoegen

Voeg nieuwe `/api/testing/*` routes toe die dezelfde functies aanroepen als de bestaande `/api/dev/*` routes.

Acceptatiecriteria:

- route-governance toont meer `TEST` routes;
- bestaande `/api/dev/*` routes blijven tijdelijk werken;
- geen functiewijziging;
- geen databasewijziging.

### R8-04C — Frontend en scripts omzetten

Zoek en wijzig alle verwijzingen naar de oude `/api/dev/*` routes in:

- frontend;
- scripts;
- regression tooling;
- documentatie;
- batchbestanden.

Acceptatiecriteria:

- nieuwe `/api/testing/*` routes worden gebruikt;
- oude `/api/dev/*` routes worden niet meer door de applicatie aangeroepen.

### R8-04D — Oude DEV aliases verwijderen

Verwijder de overgebleven `/api/dev/*` aliases nadat R8-04C is gevalideerd.

Acceptatiecriteria:

- `DEV_ONLY` is 0 of alleen expliciet behouden status-endpoint;
- Swagger toont geen testfunctionaliteit meer onder `/api/dev/*`;
- route-governance is begrijpelijk en schoon.

## Stopregels

Stop en onderzoek eerst als:

1. login niet werkt;
2. kassabonnen verdwijnen;
3. receipt import faalt;
4. route-governance niet meer werkt;
5. parsingstatus verandert zonder expliciete parserwijziging;
6. een testfixture echte gebruikersdata wijzigt.

## Aanbevolen concrete vervolgopdracht

R8-04B: voeg eerst alleen de nieuwe `/api/testing/*` aliases toe voor de 25 resterende routes. Verwijder nog niets. Daarna controleren met route-governance of de nieuwe TEST-routes zichtbaar zijn.
