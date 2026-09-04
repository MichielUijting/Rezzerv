# Rezzerv Integral Functional Acceptance Matrix

Statusdatum: 4 september 2026  
Roadmapfase: **Fase 0 — Test Trust Audit afgerond**  
Auditbaseline: `main@87846e2b257cc458c24f1ea70474ab8986bfbc81`

## 1. Doel

Dit document is de leesbare ingang van de integrale test- en acceptatiebasis van Rezzerv. De machineleesbare bron staat in:

`quality/acceptance/functional_acceptance_matrix.json`

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

- **covered** — de laag is inhoudelijk bekeken en het opgegeven bewijs dekt het bedoelde scenario voldoende;
- **partial** — er bestaat relevante automatisering, maar die bewijst nog niet de volledige laag of alle noodzakelijke varianten;
- **gap** — de vereiste laag is nog niet aantoonbaar afgedekt;
- **na** — deze laag is voor het specifieke scenario aantoonbaar niet van toepassing.

Ieder scenario heeft daarnaast `inventory` of `verified` als auditstatus.

**Belangrijk:** 100% `verified` betekent dat de audit compleet is, niet dat de testdekking 100% is. Een geverifieerd scenario kan bewust L2/L3/L4-gaten bevatten.

## 4. Fase-0 resultaat

De eerste integrale kwaliteitsinventaris bevat nu **22 scenario's**:

- **14 P0** — alle 14 inhoudelijk geverifieerd;
- **7 P1** — alle 7 kernscenario's uit de huidige productscope inhoudelijk geverifieerd;
- **1 P2** — de belangrijkste cross-cutting navigation/capability-UX doorsnede geverifieerd.

### 4.1 P0 — 14/14 geverifieerd

| ID | P0-domein | Belangrijkste resterende gat |
|---|---|---|
| P0-ACCOUNT-SESSION | Account & sessie | Echte browsergestuurde L4-reis |
| P0-ONBOARDING | Onboarding naar bruikbare app | Echte API/browser registratie-tot-app-keten |
| P0-HOUSEHOLD-MEMBERSHIP | Huishouden / uitnodiging / rol | Echte API/browser uitnodigingsreis + huishoudwissel |
| P0-AUTHORIZATION-ISOLATION | Rollen en huishoudisolatie | Niet-gemockte L4-keten |
| P0-SETTINGS-PROJECTION | Instellingen naar werkelijk gedrag | Backendopslag + PostgreSQL + gedragsprojectie |
| P0-LOCATIONS-POLICY | Locaties aan/uit | Echte PostgreSQL API + L4-configuratievarianten |
| P0-RECEIPT-INVENTORY-ALMOSTOUT | Kassa → Uitpakken → Voorraad → Bijna-op | Echte browserketen + locaties-uit variant |
| P0-KASSA-REVIEW | Kassa review / goedkeuring | Canonical fixture via echte UI naar PostgreSQL-eindstaat |
| P0-UNPACKING | Uitpakken / verwerken | Echte PostgreSQL API en L4 voor kernvarianten |
| P0-INVENTORY | Voorraadmutaties / historie | Echte API/browsercontrole + quantity-precisie/historie |
| P0-ALMOST-OUT | Bijna-op | Gebruikersweergave onderdeel van dezelfde L4-keten |
| P0-ARTICLE-IDENTITY | Huishoudartikelidentiteit | Purchase → detail → historie als echte API/browserketen |
| P0-PLATFORM-AUTHORITY | Platformrollen | Echte browser/full-stack platformauthority |
| P0-MIGRATION-STARTUP | Migratie & startup | Centraal combineren met functionele releaseacceptatie |

### 4.2 P1 — kernscope geïnventariseerd

| ID | Domein | Auditbevinding |
|---|---|---|
| P1-SHOPPING | Winkelen | Echte PostgreSQL-stack en echte zoekroute; mutatie-/afrondflow nog deels gemockt. |
| P1-GPC-ARTICLE-GROUP | GPC & Artikelgroepen | Sterke PostgreSQL GPC-import/DB-authority; huishoudspecifieke groep nog niet als één echte keten. |
| P1-DAY-ARTICLE | Dagartikelen | Sterke PostgreSQL direct-consumption service-authority; browserketen ontbreekt. |
| P1-SUPPORT-MESSAGES | Support/berichten | PostgreSQL service/API/authorization sterk; browserketen ontbreekt. |
| P1-EXTERNAL-DATABASES | Externe productdatabases | Echte stack/backendcontract aanwezig; Playwright mockt kern-API's en is dus geen L4. |
| P1-FORECASTS | Prognoses | Historische route-audit aanwezig; echte PostgreSQL prognoseberekening/projectie ontbreekt. |
| P1-STORES-IMPORT-SETTINGS | Winkels/importinstellingen | Gerichte household/source guards bestaan; setting → ingest → juiste household-keten ontbreekt. |

### 4.3 P2 — cross-cutting UX

`P2-NAVIGATION-UX` borgt dat dynamic home/settings navigation en capabilityprojectie als eigen dwarsdoorsnede zichtbaar blijven. Frontendcontracten zijn sterk; server-side sessie/permission authority moet later in dezelfde gebruikersketen worden aangesloten.

De exacte L1-L4-status en evidencepaden staan uitsluitend in de machineleesbare matrix.

## 5. Belangrijkste test-trust bevindingen

De audit heeft een terugkerend patroon blootgelegd: een workflownaam of technisch indrukwekkende testopzet zegt niet automatisch welke laag werkelijk wordt bewezen.

### 5.1 SQLite onder production-relevante namen

- `unpacking-household-location-isolation.yml` voert zijn kerncontract uit op in-memory SQLite;
- `unpacking-household-object-guard.yml` gebruikt FastAPI `TestClient`, maar ook SQLite;
- `temporal-inventory-validation.yml` test waardevolle event-/replaylogica, maar de databasegevallen zijn SQLite.

Deze tests blijven bruikbaar als L1/gerichte regressie, maar tellen niet als PostgreSQL L3.

### 5.2 Playwright met gemockte kern-API's

- authorization UI start de echte stack, maar mockt session/authorization APIs;
- receipt lifecycle/Kassa Playwright mockt household/batch/import/lifecycle APIs;
- external-recognition Playwright start de echte stack, maar mockt summary/retailers/receipt-items/search/confirmation;
- Winkelen heeft één echte zoekroute, maar de brede mutatieflow mockt shopping-list APIs.

Dit is waardevolle frontendregressie, maar geen volledige L4-keten.

### 5.3 Frontendbuild is geen full-stack acceptatie

- settings v2 valideert frontendcontracten en build, maar geen backend/PostgreSQL persistence;
- Platform Admin acceptance heeft sterke PostgreSQL backendtests en bouwt de frontend, maar draait geen platform-Playwright in die closure.

### 5.4 Workflownaam is niet altijd het bewijs-pad

`household-article-identity-slice2b4.yml` provisiont zelf geen PostgreSQL. Het echte identity-contract wordt wel op PostgreSQL uitgevoerd binnen `inventory-location-household-isolation.yml`. De matrix verwijst daarom naar het werkelijke uitvoerpad.

## 6. Wat al sterk is

Rezzerv heeft waardevolle bouwstenen die behouden en hergebruikt worden:

- echte PostgreSQL account/session API-tests;
- echte PostgreSQL authorization API-tests en household isolation;
- production-like Kassa backendgate met Alembic en DML-only runtime;
- canonical 12/12 receipt/inventoryketen met idempotentie, voorraad `0 -> 2 -> 5 -> 5 -> 1` en Bijna-op `NEE -> JA`;
- household article identity op PostgreSQL met `household_article_id` als anker;
- brede PostgreSQL platform capability-/routecontracten;
- sterke GPC, day-article en support PostgreSQL authorities;
- sterke migratie/startup gates met gescheiden migrator/runtime authority.

Het nieuwe platform bouwt hierop voort. Het doel is niet opnieuw beginnen, maar bestaand bewijs correct classificeren en ontbrekende schakels gericht bouwen.

## 7. Workflow-landschap

De bestaande workflows zijn in `docs/TEST_WORKFLOW_CLASSIFICATION.md` ingedeeld in:

- **KEEP — authority**;
- **KEEP — targeted**;
- **MERGE-CANDIDATE**;
- **RETIRE-CANDIDATE / historical evidence**.

Er wordt in Fase 0 niets verwijderd. Consolidatie gebeurt pas als uniek bewijs aantoonbaar naar een canonical authority is gemigreerd.

## 8. P0-releaseprincipe

Een P0-scenario is niet releaseveilig enkel omdat één featuretest groen is. Voor production-relevant functioneel gedrag moeten de relevante L2-, L3- en L4-bewijzen aantoonbaar aanwezig zijn.

De validator ondersteunt:

```text
python scripts/validate-functional-acceptance-matrix.py
```

voor structurele/gap-validatie tijdens de opbouw, en:

```text
python scripts/validate-functional-acceptance-matrix.py --strict-release
```

voor de uiteindelijke blokkerende releasegate in Fase 9.

## 9. Vaste configuratie- en regressievarianten

Minimaal structureel opgenomen:

- huishouden **met locaties**;
- huishouden **zonder locaties**;
- meerdere huishoudens en household isolation;
- Beheerder en Lid plus relevante beschermde/platformrollen;
- success, denial en foutpresentatie;
- retry/herverwerking en idempotentie;
- exacte niet-financiële hoeveelheden `0.404`, `1.224`, `1.234567`;
- aparte geldprecisie;
- dagartikel versus fysiek voorraadartikel;
- verse PostgreSQL en representatieve legacy-adoptie.

## 10. PO-acceptatie

Automatisering moet bewijzen dat het product technisch en functioneel volgens bekende contracten blijft werken. De PO beoordeelt daarna vooral of gedrag begrijpelijk, logisch en productmatig juist is.

Vaste cyclus:

**defect → reparatie → permanente regressietest → opname in integrale matrix/suite**

Doel is uiteindelijk een handmatige PO-smoke van circa **15–30 minuten**.

## 11. Roadmap na afsluiting Fase 0

| Fase | Doel | Exit |
|---|---|---|
| **0 — Test Trust Audit** | Bestaand bewijs betrouwbaar classificeren | **Afgerond: 22 scenario's + workflow-classificatie + implementatievolgorde** |
| **1 — Canonical test foundation** | Eén reproduceerbare PostgreSQL testbasis | Vaste migratie, rollen, resetbare fixtures |
| **2 — Testdata & scenario catalog** | Herbruikbare herkenbare scenario's | Canonieke huishoudens, rollen, bonnen, artikelen, legacydata |
| **3 — P0 backend/API coverage** | P0 logisch/API volledig afdekken | P0 L2/L3 geen onverklaarde gaten |
| **4 — P0 full-stack chains** | Echte frontend + backend + PostgreSQL | Kritieke gebruikersreizen L4 groen |
| **5 — Broad regression foundation** | Historische defecten permanent borgen | Relevante regressies in matrix/suite |
| **6 — Failure/recovery** | Fout- en herstelpaden bewijzen | Consistent gedrag bij fouten/retries |
| **7 — CI orchestration** | PR/full/deep gates organiseren | Eenduidige CI-uitkomst en evidence |
| **8 — PO Acceptance Pack** | Korte vaste PO-smoke | Alleen menselijke productbeoordeling over |
| **9 — Release Acceptance Gate** | Alles samenbrengen | `--strict-release` + releasebewijs groen |

## 12. Volgende bouwstap

**Fase 1 start nu als volgende technische opdracht.**

De eerste implementatie moet één canonical PostgreSQL 17 testfoundation maken die bestaande goede fixtures en authorities hergebruikt, met:

1. Alembic naar actuele head;
2. aparte migrator- en DML-only runtime-role;
3. deterministische reset/cleanup;
4. canonieke huishoudscenario's met locaties AAN en UIT;
5. tweede huishouden voor isolation;
6. vaste run-evidence met datastore, schemahead, scenario, commit en exitstatus.

Daarop bouwt Fase 2 de gedeelde fixtures en Fase 3/4 de echte ontbrekende API- en browserketens.
