# Rezzerv Integral Functional Acceptance Matrix

Statusdatum: 4 september 2026
Roadmapfase: **Fase 0 t/m 3 afgerond; Fase 4 in uitvoering**
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

**100% `verified` betekent dat de audit compleet is, niet dat de testdekking 100% is.** Een fase-authority mag gereed zijn terwijl een breder scenario bewust `partial` blijft wanneer die authority niet alle varianten dekt.

## 4. Fase-0 resultaat — AFGEROND

De integrale kwaliteitsinventaris bevat **22 geverifieerde scenario's**:

- **14 P0**;
- **7 P1**;
- **1 P2** cross-cutting navigation/capability-UX.

De audit bevestigde onder meer SQLite onder production-relevante namen, TestClient-contracten op SQLite, route-gemockte Playwright-tests en frontendbuilds zonder backend/databaseprojectie. Geen van die patronen telt als sterker bewijs dan het werkelijk uitvoerpad ondersteunt.

## 5. Test-trust regels

### SQLite is geen PostgreSQL L3

SQLite blijft bruikbaar voor expliciete `sqlite-test-only` contracten, maar production-relevante API/runtime acceptance gebruikt PostgreSQL.

### Playwright met gemockte kern-API's is geen echte L4

Een browsertest telt pas als L4 wanneer de normale succesroute de echte frontend, backend en PostgreSQL gebruikt. `page.route(...).fulfill(...)` voor een kern-API maakt de test een frontendcontract, geen full-stack authority.

### Frontendbuild is geen full-stack acceptatie

Een geslaagde build bewijst compileerbaarheid en bundling, niet de gebruikersketen of database-eindstaat.

### Werkelijk uitvoerpad gaat vóór workflownaam

Evidence wordt geclassificeerd op wat de workflow daadwerkelijk uitvoert, niet op de naam van workflow of bestand.

## 6. Fase 1 — Canonical PostgreSQL foundation — AFGEROND

De gedeelde foundation:

1. gebruikt PostgreSQL 17;
2. vergelijkt database-Alembic-head met de repository-head;
3. gebruikt aparte `rezzerv_migrator` en `rezzerv_app` rollen;
4. faalt als runtime schema-`CREATE` heeft;
5. seedt drie vaste huishoudscenario's;
6. bewijst deterministische reset/reseed;
7. publiceert run-evidence als CI-artifact.

Canonical scenario's:

- `acceptance-locations-on` — Beheerder + Lid, `waar_inhuis`, één space + één sublocation;
- `acceptance-locations-off` — Beheerder + Lid, `wat_inhuis`, nul locaties;
- `acceptance-isolation` — tweede huishouden, nul locaties, geen leakage.

F1-01 t/m F1-06 zijn gerealiseerd. Canonical onboarding, inventory/location en receipt/inventory authorities delen dezelfde PostgreSQL-grens.

## 7. Fase 2 — Testdata en scenario catalog — AFGEROND

De canonical catalog bevat vaste productherkenbare data voor L2/L3/L4:

- normale receipt, loyaliteitsregel, weighted `0.404 kg` en onzekere reviewregel;
- bestaand/nieuw household article, `Niet ingedeeld` en dagartikel;
- exacte quantities `0.404`, `1.224`, `1.234567` zonder generieke decimalenlimiet;
- apart financieel precisiecontract;
- Bijna-op grensgevallen 6/5/4/0 bij minimum 5;
- synthetische legacy-adoptiedata met exact quantity-behoud.

## 8. Fase 3 — P0 backend/API coverage — AFGEROND

De nieuwe F3-authorities zijn real-API/PostgreSQL authorities en controleren de relevante eindstaat. Candidate `3210cc59cb9ae3c404552b53a35bf4ddfcaf3e49` is volledig groen over de complete PR-CI-golf.

| Authority | Resultaat | Belangrijkste bewezen gedrag |
|---|---|---|
| **F3-01 Settings + location policy** | ✅ groen | echte sessie/API, rolbeperking, none/global locatiebeleid, DB/runtimeprojectie, isolation |
| **F3-02 Onboarding + membership** | ✅ groen | registratie, uitnodiging, acceptatie, sessierotatie, rollen, huishoudwissel, isolation |
| **F3-03 Uitpakken + inventory + identity** | ✅ groen als gerichte slice | locatie-toewijzing, processing, canonical identity, events, isolation, replay-idempotentie |
| **F3-04 Kassa review** | ✅ groen | review/approval, weighted `0.404`, nonphysical loyalty exclusion, cross-household denial |
| **F3-05 Bijna-op** | ✅ groen | boven/gelijk/onder/nul, locationless projectie, isolation, idempotentie, herberekening |
| **F3-06 Platform authority** | ✅ groen | none/system context, special-role authority, stacking blokkade, audit, geen huishoudescalatie |

Belangrijk: de matrix blijft conservatief. F3-03 maakt bredere varianten zoals locaties UIT, `Niet ingedeeld`, dagartikel, verbruik/correctie, same-name-different-identity en naamwijziging niet automatisch `covered`.

## 9. Fase 4 — P0 full-stack PostgreSQL chains — IN UITVOERING

L4 betekent: **echte browser + echte frontend + echte backend + echte PostgreSQL**. Kernmutaties gebeuren via de UI. Read-only API- en directe DB-controles mogen daarna bewijzen dat de projectie werkelijk is opgeslagen.

Geplande ketens:

1. **L4-01** registreren → onboarding → huishouden → instellingen → bruikbare app;
2. **L4-02** beheerder → uitnodigen → lid accepteert → rechten → huishoudwissel → isolation;
3. **L4-03** receipt → Kassa → goedkeuren → Uitpakken → locatie → Voorraad → historie → Bijna-op, locaties AAN;
4. **L4-04** dezelfde receiptketen met locaties UIT en zonder locatiekolom/-validatie;
5. **L4-05** herverwerking/idempotentie zonder dubbele voorraad/events;
6. **L4-06** aankoop → household_article → detail → historie met dezelfde canonical identity;
7. **L4-07** platformlogin → toegestane platformfunctie → verboden huishoudactie blijft verboden.

### Eerste authority: L4-01

Toegevoegd in de opvolgcandidate:

- `frontend/tests/e2e/p0-onboarding.fullstack.spec.js`;
- `frontend/playwright.fullstack.config.js`;
- `.github/workflows/p0-onboarding-fullstack-postgresql-validation.yml`.

De browser registreert een nieuw account, kiest `Wat Inhuis`, zet aantallen/Bijna-op/Winkelen aan, houdt locaties expliciet UIT, rondt het huishouden af en controleert de echte home/settingsprojectie. Daarna controleert de workflow read-only API-data en de directe PostgreSQL-eindstaat. De workflow weigert een L4-spec die `page.route()` of muterende `page.request`-calls gebruikt voor de kernflow.

**L4-01 wordt pas in de machineleesbare matrix als covered/partial opgewaardeerd nadat de nieuwe workflow groen is op de exacte PR-head.**

## 10. Sterke bestaande authorities

Onder meer behouden/hergebruikt:

- PostgreSQL account/session API-tests;
- authorization API-tests en household isolation;
- production-like Kassa backendgate met Alembic en DML-only runtime;
- canonical receipt/inventoryketen met `0 -> 2 -> 5 -> 5 -> 1`, idempotentie en Bijna-op `NEE -> JA`;
- household article identity op PostgreSQL;
- platform capability-/routecontracten;
- GPC, day-article en support PostgreSQL authorities;
- migratie/startup gates met gescheiden migrator/runtime authority.

## 11. Workflow-landschap

`docs/TEST_WORKFLOW_CLASSIFICATION.md` deelt bestaande workflows in als:

- **KEEP — authority**;
- **KEEP — targeted**;
- **MERGE-CANDIDATE**;
- **RETIRE-CANDIDATE / historical evidence**.

Consolidatie gebeurt alleen nadat uniek bewijs aantoonbaar is gemigreerd.

## 12. P0-releaseprincipe

Een P0-scenario is niet releaseveilig enkel omdat één featuretest groen is. De validator ondersteunt:

```text
python scripts/validate-functional-acceptance-matrix.py
```

voor structurele/gap-validatie tijdens de opbouw en:

```text
python scripts/validate-functional-acceptance-matrix.py --strict-release
```

voor de uiteindelijke blokkerende releasegate in Fase 9.

## 13. Vaste varianten

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

## 14. PO-acceptatie

Vaste cyclus:

**defect → reparatie → permanente regressietest → opname in integrale matrix/suite**

Doel blijft een handmatige PO-smoke van circa **15–30 minuten**, nadat technische/functionele automatisering al groen is.

## 15. Roadmap

| Fase | Status | Exit |
|---|---|---|
| **0 — Test Trust Audit** | **Afgerond** | 22 geverifieerde kernscenario's + workflow-classificatie |
| **1 — Canonical test foundation** | **Afgerond** | gedeelde PostgreSQL/Alembic/runtime authority |
| **2 — Testdata & scenario catalog** | **Afgerond** | gedeelde bonnen, artikelen, quantities, legacydata |
| **3 — P0 backend/API coverage** | **Afgerond** | F3-01 t/m F3-06 groen + bestaande sterke authorities behouden |
| **4 — P0 full-stack chains** | **In uitvoering** | echte frontend + backend + PostgreSQL L4 zonder kern-API mocks |
| **5 — Broad regression** | Nog te starten | historische defecten permanent geborgd |
| **6 — Failure/recovery** | Nog te starten | consistente fout-/retrysemantiek |
| **7 — CI orchestration** | Nog te starten | PR/full/deep/release gates |
| **8 — PO Acceptance Pack** | Nog te starten | korte menselijke productbeoordeling |
| **9 — Release Acceptance Gate** | Nog te starten | strict matrix + releasebewijs groen |
