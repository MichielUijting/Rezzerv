# Rezzerv Integral Functional Acceptance Matrix

Statusdatum: 4 september 2026  
Roadmapfase: **Fase 0 afgerond; Fase 1 in uitvoering**  
Auditbaseline: `main@87846e2b257cc458c24f1ea70474ab8986bfbc81`

## 1. Doel

Dit document is de leesbare ingang van de integrale test- en acceptatiebasis van Rezzerv. De machineleesbare bron staat in `quality/acceptance/functional_acceptance_matrix.json`.

De centrale vraag is niet hoeveel losse workflows groen zijn, maar:

> Zijn productkritische gebruikersketens aantoonbaar gedekt op de juiste testlagen, tegen de juiste PostgreSQL-runtime, inclusief rollen, huishoudconfiguraties, isolatie, foutpaden en herverwerking?

De matrix vervangt bestaande gerichte tests niet. Zij ordent bestaande evidence, maakt gaten zichtbaar en bepaalt welke aanvullende regressie- en ketentests nodig zijn.

## 2. Testlagen

| Laag | Betekenis | Hoofdvraag |
|---|---|---|
| **L1** | Unit / geïsoleerd contract | Klopt één afgebakende regel of component? |
| **L2** | Service / integratie | Werken samenwerkende backendonderdelen en datacontracten correct? |
| **L3** | API / echte runtime | Werkt het gedrag via de echte API/runtime, production-relevant op PostgreSQL? |
| **L4** | Full-stack / PO-keten | Werkt de echte gebruikersreis via frontend + backend + PostgreSQL? |

Production-relevante integrale acceptance gebruikt PostgreSQL als authority. SQLite mag uitsluitend expliciet als `sqlite-test-only` worden gelabeld en is geen vervanging voor PostgreSQL-bewijs.

## 3. Betekenis van dekkingsstatus

- **covered** — de laag is inhoudelijk bekeken en het bewijs dekt het bedoelde scenario voldoende;
- **partial** — er bestaat relevante automatisering, maar niet voor de volledige laag/varianten;
- **gap** — de vereiste laag is nog niet aantoonbaar afgedekt;
- **na** — aantoonbaar niet van toepassing.

Ieder scenario heeft daarnaast `inventory` of `verified` als auditstatus.

**100% `verified` betekent dat de audit compleet is, niet dat de testdekking 100% is.**

## 4. Fase-0 resultaat — AFGEROND

De eerste integrale kwaliteitsinventaris bevat **22 geverifieerde scenario's**:

- **14 P0**;
- **7 P1**;
- **1 P2** cross-cutting navigation/capability-UX.

### P0-gaten die de bouwvolgorde bepalen

| P0-domein | Belangrijkste resterende gat |
|---|---|
| Account & sessie | Echte browsergestuurde L4-reis |
| Onboarding | Echte API/browser registratie-tot-app-keten |
| Huishouden / uitnodiging / rol | Echte API/browser uitnodigingsreis + huishoudwissel |
| Autorisatie & huishoudisolatie | Niet-gemockte L4-keten |
| Instellingen | Backendopslag + PostgreSQL + gedragsprojectie |
| Locaties aan/uit | Echte PostgreSQL API + L4-configuratievarianten |
| Kassa → Uitpakken → Voorraad → Bijna-op | Echte browserketen + locaties-uit variant |
| Kassa review | Canonical fixture via echte UI naar PostgreSQL-eindstaat |
| Uitpakken | Echte PostgreSQL API en L4 voor kernvarianten |
| Voorraad/historie | Echte API/browsercontrole + quantity-precisie/historie |
| Bijna-op | Gebruikersweergave onderdeel van dezelfde L4-keten |
| Household article identity | Purchase → detail → historie als echte API/browserketen |
| Platformrollen | Echte browser/full-stack platformauthority |
| Migratie/startup | Centraal combineren met functionele releaseacceptatie |

### P1-kernscope

Geauditeerd: Winkelen, GPC/Artikelgroepen, Dagartikelen, Support/berichten, Externe productdatabases, Prognoses en Winkels/importinstellingen.

## 5. Belangrijkste test-trust bevindingen

### SQLite is geen PostgreSQL L3

- `unpacking-household-location-isolation.yml` gebruikt in-memory SQLite;
- `unpacking-household-object-guard.yml` gebruikt FastAPI `TestClient` maar SQLite;
- `temporal-inventory-validation.yml` bevat waardevolle temporal tests maar ook SQLite.

### Playwright met gemockte kern-API's is geen echte L4

- authorization UI mockt session/authorization APIs;
- receipt lifecycle/Kassa mockt household/batch/import/lifecycle APIs;
- external recognition mockt summary/retailers/receipt-items/search/confirmation;
- Winkelen gebruikt een echte zoekroute, maar de brede mutatieflow mockt shopping-list APIs.

### Frontendbuild is geen full-stack acceptatie

Settings v2 en Platform Admin bevatten waardevol frontend/backendbewijs, maar geen doorlopende echte browser → API → PostgreSQL-keten.

### Werkelijk uitvoerpad gaat vóór workflownaam

Het household-article identity-contract wordt betrouwbaar op PostgreSQL uitgevoerd via `inventory-location-household-isolation.yml`, ook al suggereert een andere Slice-workflownaam het meest voor de hand liggende bewijs.

## 6. Sterke bestaande authorities

Onder meer behouden/hergebruikt:

- echte PostgreSQL account/session API-tests;
- echte PostgreSQL authorization API-tests en household isolation;
- production-like Kassa backendgate met Alembic en DML-only runtime;
- canonical 12/12 receipt/inventoryketen met voorraad `0 -> 2 -> 5 -> 5 -> 1`, idempotentie en Bijna-op `NEE -> JA`;
- household article identity op PostgreSQL;
- brede PostgreSQL platform capability-/routecontracten;
- GPC, day-article en support PostgreSQL authorities;
- migratie/startup gates met gescheiden migrator/runtime authority.

## 7. Workflow-landschap

`docs/TEST_WORKFLOW_CLASSIFICATION.md` deelt bestaande workflows in als:

- **KEEP — authority**;
- **KEEP — targeted**;
- **MERGE-CANDIDATE**;
- **RETIRE-CANDIDATE / historical evidence**.

Er is niets verwijderd. Consolidatie gebeurt alleen na aantoonbare migratie van uniek bewijs.

## 8. Fase 1 — eerste canonical PostgreSQL foundation is GROEN

De eerste uitvoerbare basis staat nu in:

- `backend/app/testing/canonical_acceptance_foundation.py`;
- `.github/workflows/canonical-acceptance-foundation-validation.yml`.

De foundation:

1. gebruikt PostgreSQL 17;
2. vergelijkt database-Alembic-head met de repository-head;
3. gebruikt aparte `rezzerv_migrator` en `rezzerv_app` rollen;
4. faalt als runtime schema-`CREATE` heeft;
5. seedt drie vaste huishoudscenario's;
6. draait daarna opnieuw om reset/reseed-determinisme te bewijzen;
7. publiceert run-evidence als CI-artifact.

### Canonical scenario's

- `acceptance-locations-on` — admin + member, `waar_inhuis`, exact één space en één sublocation;
- `acceptance-locations-off` — admin + member, `wat_inhuis`, exact nul locaties;
- `acceptance-isolation` — tweede huishouden, exact nul locaties, geen leakage.

### Bewezen contract

```text
datastore=postgresql
alembic_head=20260902_01
runtime_user=rezzerv_app
migrator_user=rezzerv_migrator
runtime_create=False
migrator_create=True
scenario_count=3
locations_on_spaces=1
locations_on_sublocations=1
locations_off_spaces=0
isolation_spaces=0
CANONICAL_ACCEPTANCE_FOUNDATION_GREEN
```

De gate is geoptimaliseerd naar minimale database-/migratiedependencies; de OCR/Paddle-stack is hiervoor niet meer nodig.

### Fase-1 status

**F1-01 t/m F1-05 zijn gerealiseerd en groen. F1-06 blijft open:** bestaande goede PostgreSQL authorities moeten nog gecontroleerd op de gedeelde foundation worden aangesloten. De bewezen receipt-keten wordt daarbij niet risicovol in één grote refactor omgebouwd; migratie gebeurt authority voor authority.

## 9. P0-releaseprincipe

Een P0-scenario is niet releaseveilig enkel omdat één featuretest groen is. De validator ondersteunt:

```text
python scripts/validate-functional-acceptance-matrix.py
```

voor structurele/gap-validatie tijdens de opbouw en:

```text
python scripts/validate-functional-acceptance-matrix.py --strict-release
```

voor de uiteindelijke blokkerende releasegate in Fase 9.

## 10. Vaste varianten

Structureel opgenomen:

- huishouden met locaties;
- huishouden zonder locaties;
- tweede huishouden/household isolation;
- Beheerder en Lid plus relevante beschermde/platformrollen;
- success, denial en foutpresentatie;
- retry/herverwerking en idempotentie;
- exacte quantities `0.404`, `1.224`, `1.234567`;
- aparte geldprecisie;
- dagartikel versus fysiek voorraadartikel;
- verse PostgreSQL en representatieve legacy-adoptie.

## 11. PO-acceptatie

Vaste cyclus:

**defect → reparatie → permanente regressietest → opname in integrale matrix/suite**

Doel blijft een handmatige PO-smoke van circa **15–30 minuten**, nadat technische/functionele automatisering al groen is.

## 12. Roadmap

| Fase | Status | Exit |
|---|---|---|
| **0 — Test Trust Audit** | **Afgerond** | 22 geverifieerde kernscenario's + workflow-classificatie |
| **1 — Canonical test foundation** | **Bezig — F1-01 t/m F1-05 groen** | F1-06: bestaande PG authorities adopteren gedeelde foundation |
| **2 — Testdata & scenario catalog** | Nog te starten | gedeelde bonnen, artikelen, quantities, legacydata |
| **3 — P0 backend/API coverage** | Nog te starten | P0 L2/L3 zonder onverklaarde gaten |
| **4 — P0 full-stack chains** | Nog te starten | echte frontend + backend + PostgreSQL L4 |
| **5 — Broad regression** | Nog te starten | historische defecten permanent geborgd |
| **6 — Failure/recovery** | Nog te starten | consistente fout-/retrysemantiek |
| **7 — CI orchestration** | Nog te starten | PR/full/deep/release gates |
| **8 — PO Acceptance Pack** | Nog te starten | korte menselijke productbeoordeling |
| **9 — Release Acceptance Gate** | Nog te starten | strict matrix + releasebewijs groen |
