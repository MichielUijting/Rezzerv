# Rezzerv Integral Test Platform — Implementatiebacklog

Statusdatum: 4 september 2026  
Branch: `codex/integral-test-foundation-phase-0`  
Baseline: `main@87846e2b257cc458c24f1ea70474ab8986bfbc81`

## Doel

Deze backlog vertaalt `docs/TEST_MATRIX.md` naar concrete bouwstappen. Prioriteit wordt bepaald door productrisico en ketenimpact, niet door het aantal bestaande tests.

## Fase 0 — Test Trust Audit — AFGEROND

**Doel:** weten wat de huidige automatisering werkelijk bewijst voordat nieuwe tests worden vermenigvuldigd.

### Eindstand

- centrale Functional Acceptance Matrix: **gereed**;
- structurele validator + eigen CI-gate: **gereed**;
- P0 evidence-audit: **14/14 geverifieerd**;
- P1 kernscope-audit: **7/7 geverifieerd**;
- P2 navigation/capability-UX: **1/1 geverifieerd**;
- false-confidence audit: **gereed voor alle geïnventariseerde kernscenario's**;
- historische PostgreSQL PO-defectklassen: **in matrix/backlog verankerd**;
- workflow-landschap: **KEEP / targeted / merge-candidate / retire-candidate geclassificeerd** in `docs/TEST_WORKFLOW_CLASSIFICATION.md`;
- implementatievolgorde fasen 1–4: **vastgelegd**.

**Audit compleet betekent niet testdekking compleet.** Fase 0 heeft juist vastgesteld waar production-relevante L3- en L4-gaten zitten.

### Bevestigde false-confidence patronen

| Patroon | Voorbeeld | Werkelijke betekenis |
|---|---|---|
| SQLite onder production-relevante workflownaam | `unpacking-household-location-isolation.yml` | Gericht L1-bewijs; geen PostgreSQL L3 |
| FastAPI TestClient maar SQLite | `unpacking-household-object-guard.yml` | API-contract op SQLite; geen production-like L3 |
| Database-regressie op SQLite | `temporal-inventory-validation.yml` | Waardevolle temporal logica; geen PostgreSQL-runtimebewijs |
| Playwright + echte stack maar API's gemockt | authorization UI validation | Frontendregressie; geen echte L4 |
| Playwright receipt lifecycle met gemockte APIs | receipt lifecycle frontend regressie | UI-interactiecontract; geen Kassa/Uitpakken full-stack keten |
| Externe database Playwright mockt kern-API's | external recognition | UX-contract; geen echte external-database L4 |
| Mixed Playwright | Winkelen | echte zoekroute, maar mutatieflow is gemockt; gedeeltelijk L4 |
| Frontendcontract/build zonder backend | settings v2 information architecture | UI-structuur; geen opslaan → DB → gedragsprojectie |
| Workflownaam zonder self-contained PostgreSQL | household article identity Slice 2B4 | Het echte PG-bewijs komt uit `inventory-location-household-isolation.yml` |
| Acceptance closure bouwt frontend maar draait geen Playwright | Platform Admin 9.1.7 | Sterke PG backendcoverage; geen L4 |

### Fase-0 werkitems

| ID | Prioriteit | Werk | Status |
|---|---:|---|---|
| F0-01 | P0 | Centrale machineleesbare Functional Acceptance Matrix | **Gereed** |
| F0-02 | P0 | Structurele validator + CI-gate | **Gereed** |
| F0-03 | P0 | Alle P0 evidence inhoudelijk verifiëren | **Gereed — 14/14** |
| F0-04 | P0 | Historische PO-defectklassen koppelen | **Gereed** |
| F0-05 | P0 | False confidence inventariseren | **Gereed** |
| F0-06 | P1 | Workflows classificeren | **Gereed als migratieplan** |
| F0-07 | P0 | P0/P1/P2 implementatievolgorde vastleggen | **Gereed** |

**Fase 0 is inhoudelijk afgerond.** Er worden nog geen bestaande workflows verwijderd; consolidatie volgt alleen na aantoonbare evidence-migratie.

---

## Fase 1 — Canonical PostgreSQL test foundation — BEZIG

**Doel:** integrale tests reproduceerbaar laten starten op dezelfde production-like databasegrens.

De eerste echte foundation staat in:

- `backend/app/testing/canonical_acceptance_foundation.py`;
- `.github/workflows/canonical-acceptance-foundation-validation.yml`.

De CI draait de foundation tweemaal tegen PostgreSQL 17 om ook reset/reseed determinisme te bewijzen.

| ID | Prioriteit | Werk | Status | Huidig bewijs |
|---|---:|---|---|---|
| F1-01 | P0 | Eén geïsoleerde PostgreSQL 17 foundation | **Gereed en groen** | `datastore=postgresql`; drie canonical scenariohuishoudens |
| F1-02 | P0 | Migrator + DML-only runtime-role | **Gereed en groen** | `runtime_user=rezzerv_app`, `migrator_user=rezzerv_migrator`, runtime `CREATE=False` |
| F1-03 | P0 | Canonical Alembic-head als startvoorwaarde | **Gereed en groen** | repository-head wordt tegen `alembic_version` gecontroleerd |
| F1-04 | P0 | Deterministische reset/reseed | **Gereed en groen** | tweede foundationrun levert exact dezelfde scenario-eindstaat |
| F1-05 | P0 | Run identity/evidence | **Gereed en groen** | candidate SHA, datastore, database, head, rollen en scenarioresultaat + CI-artifact |
| F1-06 | P0 | Bestaande goede PG fixtures achter één gedeelde interface brengen | **Open** | receipt/onboarding/inventory authorities moeten de foundation gaan consumeren |

### Canonical scenario's die nu bestaan

1. `acceptance-locations-on`
   - regulier huishouden;
   - admin + member;
   - `primary_use_case=waar_inhuis`;
   - exact één `Voorraadkast` en één `Bovenste plank`.
2. `acceptance-locations-off`
   - regulier huishouden;
   - admin + member;
   - `primary_use_case=wat_inhuis`;
   - exact nul locaties.
3. `acceptance-isolation`
   - tweede regulier huishouden;
   - admin + member;
   - exact nul locaties;
   - controle dat data van het locaties-AAN-huishouden niet lekt.

### Laatste bewezen foundationcontract

De geoptimaliseerde CI gebruikt alleen de minimale database-/migratiedependencies in plaats van de volledige OCR/Paddle-stack. De gate blijft inhoudelijk gelijk en moet eindigen met:

```text
datastore=postgresql
runtime_create=False
migrator_create=True
scenario_count=3
locations_on_spaces=1
locations_on_sublocations=1
locations_off_spaces=0
isolation_spaces=0
CANONICAL_ACCEPTANCE_FOUNDATION_GREEN
```

**Fase 1 is nog niet volledig klaar.** Eerst moet F1-06 aantonen dat bestaande PostgreSQL-tests de nieuwe foundation daadwerkelijk kunnen hergebruiken, zodat geen nieuw parallel fixture-eiland ontstaat.

---

## Fase 2 — Testdata en scenario catalog

**Doel:** vaste productherkenbare scenario's die door L2/L3/L4 worden gedeeld.

### Verplichte huishoudscenario's

1. regulier huishouden — **locaties AAN**;
2. regulier huishouden — **locaties UIT**;
3. tweede regulier huishouden voor isolation-tests;
4. Beheerder;
5. Lid;
6. relevante legacy-/beschermde rolcontexten volgens de actuele runtime-authority;
7. systeemhuishouden `0` uitsluitend waar het contract dit expliciet vereist.

De eerste drie huishoudscenario's plus admin/member bestaan inmiddels in de Fase-1 foundation.

### Nog toe te voegen datafixtures

- kassabon met normale fysieke artikelen;
- kassabon met koop-/spaarzegels of andere niet-fysieke regels;
- onzekere productmatch;
- dagartikel;
- bestaand household article;
- nieuw household article;
- Artikelgroep `Niet ingedeeld`;
- hoeveelheden `0.404`, `1.224`, `1.234567` zonder generieke quantity-afronding;
- financiële waarden met afzonderlijk geldprecisiecontract;
- voorraad boven en onder Bijna-op-drempel;
- representatieve legacy-adoptiedata zonder persoonsgegevens/productiedata.

---

## Fase 3 — P0 backend/API coverage

Uitvoeringsvolgorde op basis van de audit:

1. **Settings + location policy** — instelling echt opslaan en gedrag sturen;
2. **Onboarding + household membership** — servicebewijs naar echte API-authority;
3. **Uitpakken + inventory + article identity** — SQLite/API-contracten naar echte PostgreSQL L3;
4. **Kassa review** — canonical fixture via echte review/approval API naar DB-eindstaat;
5. **Almost-out API/projectie** — technische keten koppelen aan uitleesbare gebruikersstatus;
6. **Platform authority** — sterke backenddekking tot volledige API-authority;
7. **Account/session + authorization** — bestaande sterke L3 als regression authority behouden;
8. **Migration/startup** — bestaande sterke technische foundation behouden.

Per P0-scenario moet L2/L3 de werkelijke eindtoestand controleren, niet alleen HTTP- of procesexitcodes.

---

## Fase 4 — P0 full-stack PostgreSQL chains

L4 betekent: echte browser + echte frontend + echte backend + echte PostgreSQL. Geen `page.route(...).fulfill(...)` voor kern-API's op de normale succesroute.

- **L4-01:** registreren → onboarding → huishouden → instellingen → bruikbare app.
- **L4-02:** beheerder → uitnodigen → lid accepteert → rechten → huishoudwissel → isolation.
- **L4-03:** receipt → Kassa → goedkeuren → Uitpakken → locatie → Voorraad → historie → Bijna-op, locaties AAN.
- **L4-04:** dezelfde keten met locaties UIT en zonder locatiekolom/-validatie.
- **L4-05:** herverwerking/idempotentie zonder dubbele voorraad/events.
- **L4-06:** aankoop → household_article → detail → historie met dezelfde canonical identity.
- **L4-07:** platformlogin → toegestane platformfunctie → verboden huishoudactie blijft verboden.

---

## Fase 5 — Historische regressiefoundation

Iedere bevestigde productbug krijgt de laagste zinvolle permanente regressietest, aanvullende L3/L4-dekking waar samenhang nodig is en een verwijzing in de matrix.

Eerste verplichte defectklassen uit de PostgreSQL PO-ronde:

- boolean/runtime-portability;
- JSON serialisatie vanuit PostgreSQL-resultaten;
- receipt worker fail-closed status;
- receipt source runtime wiring;
- quantities zonder generieke decimalenlimiet;
- gerichte restauratie van historisch beschadigde quantity-data;
- household location policy consequent in backend en UI;
- locatievrije Uitpakken-verwerking;
- `Niet ingedeeld` als geldige Uitpakken-keuze;
- household article canonical naam/identiteit;
- history sortering/NULL-semantiek op PostgreSQL;
- history events zonder locatie waar het huishouden geen locaties gebruikt;
- conditionele `Locaties`-tab;
- standaard gebruikersfeedback bij API-fouten.

---

## Fase 6 — Failure & recovery

Minimaal: 401/403, functionele 4xx, gecontroleerde 5xx, timeout/tijdelijke fout, ongeldige import, retry/dubbele request, onderbroken keten, veilige hervatting, standaard feedback en databaseconsistentie na fout.

---

## Fase 7 — CI orchestration

- **PR Fast Regression:** snelle L1/L2 + relevante L3/L4.
- **Full Regression:** complete functionele regressie voor integratiekandidaat/main.
- **Deep / Nightly:** zwaardere varianten, legacydata, recovery en combinaties.
- **Release Acceptance:** PostgreSQL + migraties + alle P0 L2/L3/L4 + build/startup + PO-status.

Featuregerichte workflows worden pas geconsolideerd volgens `docs/TEST_WORKFLOW_CLASSIFICATION.md` nadat vervangend bewijs stabiel is.

---

## Fase 8 — PO Acceptance Pack

Doelduur: circa **15–30 minuten**. De PO beoordeelt primair begrijpelijkheid, logische gebruikersflow, zichtbaarheid en productmatig gewenst gedrag; technische regressie hoort al groen te zijn.

---

## Fase 9 — Release Acceptance Gate

De finale gate activeert:

```text
python scripts/validate-functional-acceptance-matrix.py --strict-release
```

Een release is pas kandidaat voor PO-GO wanneer alle vereiste P0-lagen, PostgreSQL/migratie/startup en build/runtime groen zijn en de PO-acceptatiestatus expliciet is vastgelegd. Automatisering geeft nooit zelfstandig merge-toestemming.
