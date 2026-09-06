# Rezzerv Integral Functional Acceptance Matrix

Statusdatum: 6 september 2026
Roadmapfase: **Fase 0 t/m 3 afgerond; Fase 4 in uitvoering — L4-01 t/m L4-06 gerealiseerd**
Auditbaseline: `main@e43224a74dcc0b8f7aa74bac8f636176d09360ed`

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

De F3-authorities zijn real-API/PostgreSQL authorities en controleren de relevante eindstaat.

| Authority | Resultaat | Belangrijkste bewezen gedrag |
|---|---|---|
| **F3-01 Settings + location policy** | ✅ groen | echte sessie/API, rolbeperking, none/global locatiebeleid, DB/runtimeprojectie, isolation |
| **F3-02 Onboarding + membership** | ✅ groen | registratie, uitnodiging, acceptatie, sessierotatie, rollen, huishoudwissel, isolation |
| **F3-03 Uitpakken + inventory + identity** | ✅ groen als gerichte slice | locatie-toewijzing, processing, canonical identity, events, isolation, replay-idempotentie |
| **F3-04 Kassa review** | ✅ groen | review/approval, weighted `0.404`, nonphysical loyalty exclusion, cross-household denial |
| **F3-05 Bijna-op** | ✅ groen | boven/gelijk/onder/nul, locationless projectie, isolation, idempotentie, herberekening |
| **F3-06 Platform authority** | ✅ groen | none/system context, special-role authority, stacking blokkade, audit, geen huishoudescalatie |

Belangrijk: de matrix blijft conservatief. Een gerichte F3-authority maakt bredere varianten niet automatisch `covered`.

## 9. Fase 4 — P0 full-stack PostgreSQL chains — IN UITVOERING

L4 betekent: **echte browser + echte frontend + echte backend + echte PostgreSQL**. Kernmutaties gebeuren via de UI. Read-only API- en directe DB-controles mogen daarna bewijzen dat de projectie werkelijk is opgeslagen.

### Actuele stand

| ID | Keten | Status |
|---|---|---|
| **L4-01** | registreren → onboarding → huishouden → instellingen → bruikbare app | ✅ Gereed en groen |
| **L4-02** | beheerder → uitnodigen → lid accepteert → rechten → huishoudwissel → isolation | ✅ Gereed en groen |
| **L4-03** | receipt → Kassa → goedkeuren → Uitpakken → locatie → Voorraad → historie → Bijna-op, locaties AAN | ✅ Gereed; gemerged via PR #366 |
| **L4-04** | dezelfde receiptketen met locaties UIT en zonder locatiekolom/-validatie | ✅ Gereed; gemerged via PR #368 |
| **L4-05** | herverwerking/idempotentie zonder dubbele voorraad/events | ✅ Gereed; gemerged via PR #369 |
| **L4-06** | aankoop → household_article → detail → historie zonder identiteitsverwisseling | ✅ Authority groen op PR #370 |
| **L4-07** | platformlogin → toegestane platformfunctie → verboden huishoudactie blijft verboden | ⏳ Eerstvolgende L4-scope |

### L4-01 — onboarding

De browser registreert een nieuw account, doorloopt de echte onboarding en controleert de home/settingsprojectie tegen PostgreSQL.

Authority:

- `frontend/tests/e2e/p0-onboarding.fullstack.spec.js`;
- `.github/workflows/p0-onboarding-fullstack-postgresql-validation.yml`.

### L4-02 — household membership en isolation

Twee echte browsercontexten bewijzen uitnodigen, accepteren, rolprojectie, huishoudwissel en isolation.

Authority:

- `frontend/tests/e2e/p0-household-membership.fullstack.spec.js`;
- `.github/workflows/p0-household-membership-fullstack-postgresql-validation.yml`.

### L4-03 — locaties AAN

De canonical receiptketen bewijst Kassa, goedkeuren, Uitpakken, locatiekeuze, Voorraad, artikelinstellingen, Afboeken en Bijna-op via de echte stack. Tijdens deze keten is tevens de synthetische `live::...` identity-adoptie permanent gerepareerd.

### L4-04 — locaties UIT

PR #368 bewijst dat bij `location_tracking_level=none` de locatiekolom/-keuze niet verschijnt, geen locatievalidatie wordt afgedwongen en locationless verwerking/events geldig blijven.

### L4-05 — herverwerking/idempotentie

PR #369 bewijst dat een dubbele/vertraagde gebruikersactie op `Naar voorraad` niet tot dubbele voorraad of events leidt en dat replay dezelfde `processed_event_id` behoudt.

### L4-06 — canonical article identity

Authority:

- `frontend/tests/e2e/p0-article-identity-history.fullstack.spec.js`;
- `scripts/acceptance/l4_06_article_identity_history.py`;
- `.github/workflows/p0-article-identity-history-fullstack-postgresql-validation.yml`.

Bewezen op de echte browser/frontend/backend/PostgreSQL-keten:

1. twee verschillende aankoopregels houden verschillende canonical `household_article`-UUID's;
2. beide kunnen dezelfde huishoudnaam krijgen zonder identity-merge;
3. een naamwijziging blijft na reload aan dezelfde UUID gekoppeld;
4. elk Historie-scherm toont uitsluitend het eigen purchase-event;
5. purchase-import-regels, inventory en inventory-events blijven exact aan de juiste UUID gekoppeld;
6. runtime is DML-only en de browser gebruikt geen core API mocks of muterende `page.request`.

De browser- en PostgreSQL-authority was volledig groen op candidate `aaed274885943e2abcbdab50aff80780e697ae1f`. De governancewijzigingen op PR #370 doorlopen opnieuw exact-head CI voordat de PR merge-klaar kan worden verklaard.

### Eerstvolgende L4

**L4-07 — platformauthority via de echte browser.** Daarmee wordt de laatste van de zeven geplande P0-L4-authorities gebouwd.

## 10. Sterke bestaande authorities

Onder meer behouden/hergebruikt:

- PostgreSQL account/session API-tests;
- authorization API-tests en household isolation;
- production-like Kassa backendgate met Alembic en DML-only runtime;
- canonical receipt/inventoryketen met idempotentie en Bijna-op;
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
| **4 — P0 full-stack chains** | **In uitvoering — 6/7 authorities gerealiseerd** | L4-07 resteert |
| **5 — Broad regression** | Gedeeltelijk opgebouwd | historische defecten permanent geborgd |
| **6 — Failure/recovery** | Gedeeltelijk opgebouwd | consistente fout-/retrysemantiek |
| **7 — CI orchestration** | Gedeeltelijk opgebouwd | PR/full/deep/release gates |
| **8 — PO Acceptance Pack** | Nog te bouwen | korte menselijke productbeoordeling |
| **9 — Release Acceptance Gate** | Voorbereid, nog niet actief | strict matrix + releasebewijs groen |
