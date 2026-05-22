# R8-01 — API-classificatie stap 1

Status: concept-inventarisatie
Scope: documentatie en governance
Runtime-impact: geen
Database-impact: geen
Parser/OCR-impact: geen

## Doel

Deze inventarisatie classificeert de zichtbare Swagger/API-routes zodat Rezzerv onderscheid kan maken tussen productie-endpoints, beheertools, testdiagnostiek, tijdelijke ontwikkeltools, legacy-routes en verwijderkandidaten.

Deze stap verwijdert nog niets. Dit document is bedoeld als beslisbasis voor de PO en het scrumteam.

## Classificaties

| Classificatie | Betekenis | Actie nu |
|---|---|---|
| PROD | Nodig voor normale applicatiewerking | behouden |
| ADMIN | Beheer/reparatie/backfill, niet voor normale gebruiker | behouden maar afschermen/ordenen |
| TEST | Regressie, diagnose of testinformatie | behouden maar scheiden van productie |
| DEV_ONLY | Lokale ontwikkelhulpmiddelen of fixture-generators | kandidaat voor uitschakeling in gewone runtime |
| LEGACY | Historische of vervangen route | nader onderzoeken |
| REMOVE_CANDIDATE | Waarschijnlijk niet meer nodig of risicovol in runtime | alleen verwijderen na bewijs |

## Eerste classificatie op basis van huidige Swagger-runtime

### Systeem

| Route/patroon | Classificatie | Reden |
|---|---|---|
| `/api/health` | PROD | Healthcheck voor backend |
| `/api/version` | PROD | Versiecontrole/runtime-identificatie |

### Kassabon — productieflow

| Route/patroon | Classificatie | Reden |
|---|---|---|
| `/api/receipts` | PROD | Lijst ingelezen kassabonnen |
| `/api/receipts/import` | PROD | Kassabon importeren |
| `/api/receipts/{receipt_table_id}` | PROD | Kassabondetail ophalen |
| `/api/receipts/{receipt_table_id}/preview` | PROD | Kassabonpreview |
| `/api/receipts/{receipt_table_id}/lines` | PROD | Kassabonregel toevoegen |
| `/api/receipts/{receipt_table_id}/lines/{line_id}` | PROD | Kassabonregel aanpassen |
| `/api/receipts/{receipt_table_id}/approve` | PROD | Gebruikersactie op kassabon |
| `/api/receipts/{receipt_table_id}/reparse` | ADMIN | Reparatie/herverwerking, niet gewone kernflow |
| `/api/receipts/reparse-suspicious` | ADMIN | Beheerroutine voor verdachte bonnen |
| `/api/receipts/delete` | PROD | Gebruikersactie verwijderen/archiveren |
| `/api/receipts/{receipt_table_id}/debug-export` | TEST | Diagnose-export, niet productiefunctionaliteit |

### Kassabon — bronnen en externe import

| Route/patroon | Classificatie | Reden |
|---|---|---|
| `/api/receipt-sources` | PROD | Bronnen beheren/listen |
| `/api/receipt-sources/email-route` | PROD | E-mailroute tonen |
| `/api/receipt-sources/gmail-status` | PROD | Gmailstatus tonen |
| `/api/receipts/gmail/connect-url` | PROD | Gmailkoppeling starten |
| `/api/receipts/gmail/callback` | PROD | OAuth callback |
| `/api/receipts/gmail/sync` | ADMIN | Handmatige synchronisatie/beheeractie |
| `/api/receipts/email-import` | PROD | Import via e-mail |
| `/api/receipts/inbound` | PROD | Inbound e-mailontvangst |
| `/api/receipts/share-import` | PROD | Share-import |
| `/api/receipts/share-target` | PROD | Share-target import |
| `/api/receipts/source-scan` | ADMIN | Bronscan is beheer/diagnose |

### Kassabon — status en baseline

| Route/patroon | Classificatie | Reden |
|---|---|---|
| `/api/admin/recompute-receipt-statuses` | ADMIN | Backfill/herberekening |
| `/api/admin/validate-receipt-status-baseline` | TEST | Baselinevalidatie |
| `/api/admin/diagnose-receipt-status-baseline` | TEST | Baseline-diagnose |
| `/api/dev/receipts/po-status-labels` | TEST | Statusdiagnose zichtbaar onder dev; moet later naar testing/admin worden verplaatst |
| `receipt_status_baseline_service_v4.py` | SSOT | Enige bron voor PO-statusbepaling |

### Testing-routes

| Route/patroon | Classificatie | Reden |
|---|---|---|
| `/api/testing/receipt-parser-diagnosis` | TEST | Read-only parserdiagnose |
| `/api/testing/receipt-parser-diagnosis/download` | TEST | Downloadbare diagnose |
| `/api/testing/receipt-db-snapshot` | TEST | Database snapshot voor analyse |
| `/api/testing/receipt-db-snapshot/download` | TEST | Downloadbare snapshot |

### Voorraad, artikelen en household

| Route/patroon | Classificatie | Reden |
|---|---|---|
| `/api/auth/login` | PROD | Login |
| `/api/auth/context` | PROD | Gebruikerscontext |
| `/api/auth/capabilities` | PROD | Capabilities/autorisatie |
| `/api/household` | PROD | Huishouden ophalen |
| `/api/household/name` | PROD | Huishouden hernoemen |
| `/api/household/members` | PROD | Ledenbeheer |
| `/api/household/role-audit` | ADMIN | Audit-informatie |
| `/api/household/permissions/{permission_key}` | PROD | Permission policy |
| `/api/household/automation-settings` | PROD | Instellingen |
| `/api/household/almost-out-settings` | PROD | Instellingen |
| `/api/household/store-import-settings` | PROD | Instellingen |
| `/api/settings/article-field-visibility` | PROD | UI/veldinstellingen |
| `/api/settings/privacy-data-sharing` | PROD | Privacy-instellingen |
| `/api/household-articles/*` | PROD | Hoofdresource huishoudartikelen |
| `/api/articles/{article_id}` | LEGACY | Adapter/oud artikelanker; later vervangen door household_article |
| `/api/articles/household-details` | LEGACY | Oude detailroute/adaptielaag |
| `/api/inventory-events` | PROD | Voorraadevent mutatie |
| `/api/inventory-transfers` | PROD | Voorraadtransfer |
| `/api/spaces` | PROD | Ruimtes |
| `/api/sublocations` | PROD | Sublocaties |

### Productverrijking

| Route/patroon | Classificatie | Reden |
|---|---|---|
| `/api/products/sources` | PROD | Productbronnen tonen |
| `/api/products/identify` | PROD | Productidentificatie |
| `/api/products/enrich` | PROD | Productverrijking |
| `/api/products/enrich/retry` | ADMIN | Retry/beheeractie |
| `/api/articles/{article_id}/enrich` | LEGACY | Oud artikelanker |
| `/api/household-articles/{household_article_id}/enrich` | PROD | Nieuw functioneel anker |

### Store import / purchase import

| Route/patroon | Classificatie | Reden |
|---|---|---|
| `/api/store-providers` | PROD | Winkelproviders tonen |
| `/api/store-connections` | PROD | Winkelkoppelingen |
| `/api/store-connections/{connection_id}/pull-purchases` | ADMIN | Handmatige pull/beheer |
| `/api/purchase-import-batches/{batch_id}` | PROD | Importbatch bekijken |
| `/api/purchase-import-batches/{batch_id}/prefill` | PROD | Batch voorbereiden |
| `/api/purchase-import-batches/{batch_id}/process` | PROD | Batch verwerken |
| `/api/purchase-import-lines/{line_id}/review` | PROD | Reviewregel |
| `/api/purchase-import-lines/{line_id}/map` | PROD | Mapping |
| `/api/purchase-import-lines/{line_id}/create-article` | PROD | Artikel aanmaken vanuit importregel |
| `/api/purchase-import-lines/{line_id}/target-location` | PROD | Doellocatie instellen |
| `/api/purchase-import-batches/{batch_id}/complete-review` | PROD | Review afronden |
| `/api/dev/purchase-import-batches/{batch_id}/diagnostics` | TEST | Dev-diagnose, later naar testing verplaatsen |

### Dev-only en regressie

| Route/patroon | Classificatie | Reden |
|---|---|---|
| `/api/dev/status` | DEV_ONLY | Ontwikkelstatus |
| `/api/dev/reset-data` | DEV_ONLY | Risicovol: kan data resetten |
| `/api/dev/browser-regression/reset-fixture` | DEV_ONLY | Browserfixture reset |
| `/api/dev/generate-demo-data` | DEV_ONLY | Datagenerator |
| `/api/dev/generate-layer1-receipt-fixture` | DEV_ONLY | Testfixture generator |
| `/api/dev/generate-receipt-export-fixture` | DEV_ONLY | Testfixture generator |
| `/api/dev/export-receipt-export-fixture` | TEST | Export testfixture |
| `/api/dev/generate-large-dataset` | DEV_ONLY | Datagenerator |
| `/api/dev/generate-article-testdata` | DEV_ONLY | Testdatagenerator |
| `/api/dev/regression/*` | DEV_ONLY | Lokale regressietooling |
| `/api/dev/run-smoke-tests` | TEST | Test-runner, niet productie |
| `/api/dev/run-regression-tests` | TEST | Test-runner, niet productie |
| `/api/dev/run-layer1-tests` | TEST | Test-runner, niet productie |
| `/api/dev/run-layer2-tests` | TEST | Test-runner, niet productie |
| `/api/dev/run-layer3-tests` | TEST | Test-runner, niet productie |
| `/api/dev/run-parsing-fixture-tests` | TEST | Test-runner |
| `/api/dev/run-parsing-raw-tests` | TEST | Test-runner |
| `/api/dev/test-report` | TEST | Testrapport |
| `/api/dev/test-status` | TEST | Teststatus |
| `/api/dev/test-report/latest` | TEST | Laatste testrapport |
| `/api/dev/spaces` | DEV_ONLY | Dev-mutatie naast productie-route |
| `/api/dev/sublocations` | DEV_ONLY | Dev-mutatie naast productie-route |
| `/api/dev/inventory` | DEV_ONLY | Dev-mutatie naast productie-route |
| `/api/dev/articles/archive` | DEV_ONLY | Dev-mutatie naast productie-route |
| `/api/dev/diagnostics/store-location-options` | TEST | Diagnose |
| `/api/dev/diagnostics/store-process-validation` | TEST | Diagnose |
| `/api/dev/household/*` | DEV_ONLY | Dev-variant van household instellingen |
| `/api/dev/articles/{article_id}/automation-override` | DEV_ONLY | Dev-variant van artikelinstelling |

## Eerste governance-conclusies

1. `/api/dev/reset-data` is de hoogste risicoroute omdat deze dataverlies kan veroorzaken als hij in gewone runtime zichtbaar blijft.
2. Dev-mutaties naast productie-mutaties veroorzaken verwarring en regressierisico.
3. Test-runners en fixture-generators horen niet in dezelfde Swagger-groep als productie-API's.
4. Legacy artikelroutes moeten voorlopig blijven bestaan zolang frontend of adapters ze nog gebruiken, maar ze moeten expliciet als LEGACY gemarkeerd worden.
5. Receipt-status heeft een duidelijke SSOT: `receipt_status_baseline_service_v4.py`. Alle andere statusroutes moeten read-only of admin/test zijn.

## Voorstel voor Stap 2

Maak nog geen deletions. Voeg eerst een route-governance laag toe:

- productie Swagger standaard tonen;
- dev/test/admin alleen tonen met expliciete ontwikkelmodus;
- risicoroutes zoals reset/generate apart markeren;
- endpointmanifest genereren uit FastAPI routes;
- per route vastleggen: owner, classificatie, write/read-only, datarisico, PO-zichtbaarheid.

## Stopregel

Geen endpoint verwijderen zonder bewijs dat:

1. het niet door frontend wordt aangeroepen;
2. het niet door tests of scripts wordt gebruikt;
3. er een alternatief bestaat of de route werkelijk overbodig is;
4. de PO expliciet akkoord is met verwijdering of verberging.
