# Rezzerv Integral Test Platform — Implementatiebacklog

Statusdatum: 4 september 2026  
Branch: `codex/integral-test-foundation-phase-0`  
Baseline: `main@87846e2b257cc458c24f1ea70474ab8986bfbc81`

## Doel

Deze backlog vertaalt `docs/TEST_MATRIX.md` naar concrete bouwstappen. Prioriteit wordt bepaald door productrisico en ketenimpact, niet door het aantal bestaande tests.

## Fase 0 — Test Trust Audit

**Doel:** weten wat de huidige automatisering werkelijk bewijst voordat nieuwe tests worden vermenigvuldigd.

### Huidige voortgang

- centrale Functional Acceptance Matrix: **gereed**;
- structurele validator + eigen CI-gate: **gereed en groen**;
- P0 evidence-audit: **14 van 14 scenario's geverifieerd (100%)**;
- false-confidence audit voor P0: **gereed**;
- historische PostgreSQL PO-defectklassen: **in de matrix/backlog verankerd**;
- P1/P2 detailaudit en workflow-consolidatie: **nog open**.

**100% audit is niet 100% testdekking.** De audit heeft juist meerdere echte L3/L4-gaten aangetoond. Die vormen de bouwopdracht voor fasen 1–4.

### Bevestigde false-confidence patronen

| Patroon | Voorbeeld | Werkelijke betekenis |
|---|---|---|
| SQLite onder production-relevante workflownaam | `unpacking-household-location-isolation.yml` | Gericht L1-bewijs; geen PostgreSQL L3 |
| FastAPI TestClient maar SQLite | `unpacking-household-object-guard.yml` | API-contract op SQLite; geen production-like L3 |
| Database-regressie op SQLite | `temporal-inventory-validation.yml` | Waardevolle temporal logica; geen PostgreSQL-runtimebewijs |
| Playwright + echte stack maar API's gemockt | authorization UI validation | Frontendregressie; geen echte L4 |
| Playwright receipt lifecycle met gemockte APIs | receipt lifecycle frontend regressie | UI-interactiecontract; geen Kassa/Uitpakken full-stack keten |
| Frontendcontract/build zonder backend | settings v2 information architecture | UI-structuur; geen opslaan → DB → gedragsprojectie |
| Workflownaam zonder self-contained PostgreSQL | household article identity Slice 2B4 | Het echte PG-bewijs komt uit `inventory-location-household-isolation.yml` |
| Acceptance closure bouwt frontend maar draait geen Playwright | Platform Admin 9.1.7 | Sterke PG backendcoverage; geen L4 |

### Fase-0 werkitems

| ID | Prioriteit | Werk | Status | Exitbewijs |
|---|---:|---|---|---|
| F0-01 | P0 | Centrale machineleesbare Functional Acceptance Matrix invoeren | **Gereed** | `quality/acceptance/functional_acceptance_matrix.json` |
| F0-02 | P0 | Structurele validator + CI-gate invoeren | **Gereed en groen** | validator + workflow + CI-evidence |
| F0-03 | P0 | Alle huidige P0 evidence inhoudelijk verifiëren | **Gereed — 14/14** | alle P0-scenario's `verified` |
| F0-04 | P0 | Historische PO-defectklassen aan permanente scenario's koppelen | **Gereed voor huidige PostgreSQL PO-ronde** | locatiebeleid, quantity precision, error feedback, article history, idempotentie e.d. in roadmap |
| F0-05 | P0 | False confidence inventariseren | **P0 gereed** | bovenstaande gap-analyse + matrixclassificatie |
| F0-06 | P1 | Dubbele, obsolete en PR-specifieke workflows classificeren | **Open** | keep/merge/retire-lijst, nog zonder verwijdering |
| F0-07 | P0 | Definitieve P0/P1/P2 implementatievolgorde vastleggen | **P0-volgorde gereed; P1/P2 nog afronden** | fase-0 exitrapport |

### Fase-0 exit

De P0-audit is inhoudelijk klaar. Fase 0 als geheel sluit wanneer P1/P2 voldoende zijn geïnventariseerd en bestaande workflows een `keep / merge / retire`-classificatie hebben. Er wordt in Fase 0 nog niets verwijderd alleen omdat het dubbel of oud lijkt.

---

## Fase 1 — Canonical PostgreSQL test foundation

**Doel:** alle integrale tests reproduceerbaar laten starten op dezelfde production-like databasegrens.

| ID | Prioriteit | Werk | Acceptatiecriterium |
|---|---:|---|---|
| F1-01 | P0 | Eén geïsoleerde PostgreSQL 17 teststack als canonical foundation | Geen normale P0-integratietest gebruikt SQLite als productie-approximation |
| F1-02 | P0 | Migrator- en DML-only runtime-role als vaste testgrens | Runtime kan business-DML uitvoeren en schema-DDL niet |
| F1-03 | P0 | Canonical Alembic-head als startvoorwaarde | Iedere integrale run bewijst schemahead vóór businessscenario |
| F1-04 | P0 | Deterministische reset/cleanup | Iedere run start en eindigt schoon zonder productie/local volume te raken |
| F1-05 | P0 | Test-run identity/evidence | Resultaat noemt datastore, schemahead, scenario, commit en exitstatus |

Bestaande canonical receipt-chain en PostgreSQL onboarding/inventory-fixtures worden hergebruikt. Het doel is één foundation, niet nóg een parallel testframework.

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

### Verplichte datafixtures

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

De P0-audit bepaalt nu de uitvoeringsvolgorde:

1. **Settings + location policy** — grootste cross-layer gat; instelling moet echt worden opgeslagen en gedrag sturen;
2. **Onboarding + household membership** — servicebewijs bestaat, echte API authority ontbreekt nog;
3. **Uitpakken + inventory + article identity** — bestaande SQLite/API-contracten naar echte PostgreSQL L3 brengen;
4. **Kassa review** — canonical fixture via echte review/approval API naar aantoonbare DB-eindstaat;
5. **Almost-out API/projectie** — technische keten koppelen aan uitleesbare gebruikersstatus;
6. **Platform authority** — bestaande sterke backenddekking tot volledige API-authority aanscherpen;
7. **Account/session + authorization** — bestaande sterke L3 als blijvende regression authority behouden;
8. **Migration/startup** — bestaande sterke technische foundation behouden.

Per P0-scenario moet L2/L3 de werkelijke eindtoestand controleren, niet alleen een HTTP- of procesexitcode.

---

## Fase 4 — P0 full-stack PostgreSQL chains

L4 betekent: echte browser + echte frontend + echte backend + echte PostgreSQL. Geen `page.route(...).fulfill(...)` voor kern-API's op de normale succesroute.

### L4-01 — Nieuwe gebruiker naar bruikbare app

`registreren -> onboarding -> huishouden -> instellingen -> bruikbare home/context`

### L4-02 — Huishouden en autorisatie

`beheerder -> uitnodigen -> lid accepteert -> rechten -> huishoudwissel -> isolation`

### L4-03 — Receipt/inventory, locaties AAN

`ZIP/EML -> Kassa -> goedkeuren -> Uitpakken -> locatie -> verwerken -> Voorraad -> historie -> Bijna-op`

### L4-04 — Receipt/inventory, locaties UIT

Dezelfde keten, maar zonder locatiekolom/-keuze en zonder foutieve locatievalidatie. Dit borgt de defectklasse uit de PostgreSQL PO-check.

### L4-05 — Herverwerking/idempotentie

Dezelfde receipt opnieuw verwerken verandert voorraad niet dubbel en creëert geen foutieve events.

### L4-06 — Article identity/history

`aankoop -> household_article -> detail -> historie` houdt dezelfde canonieke identiteit vast.

### L4-07 — Platform authority

`platformlogin -> toegestane platformfunctie -> verboden huishoudactie blijft verboden`, met echte backend en PostgreSQL.

---

## Fase 5 — Historische regressiefoundation

Iedere bevestigde productbug krijgt:

1. de laagste zinvolle permanente regressietest;
2. aanvullende L3/L4-dekking wanneer de bug alleen in samenhang ontstond;
3. verwijzing vanuit de Functional Acceptance Matrix.

Eerste verplichte defectklassen uit de PostgreSQL PO-ronde:

- boolean/runtime-portability;
- JSON serialisatie vanuit PostgreSQL-resultaten;
- receipt worker fail-closed status;
- receipt source runtime wiring;
- quantities zonder generieke decimalenlimiet;
- bestaande beschadigde quantity-data gericht herstellen;
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

Minimaal testen:

- 401 en 403;
- functionele 4xx;
- gecontroleerde 5xx;
- timeout/tijdelijke dependencyfout;
- lege of ongeldige import;
- dubbele request/retry;
- gedeeltelijk onderbroken keten;
- veilige hervatting zonder dubbele mutatie;
- standaard gebruikersfeedback zonder technische lekkage;
- databaseconsistentie na fout.

---

## Fase 7 — CI orchestration

### PR Fast Regression

Snelle L1/L2 plus relevante L3/L4 op basis van geraakt scenario.

### Full Regression

Complete functionele regressie voor integratiekandidaat/main.

### Deep / Nightly

Zwaardere varianten, legacydata, recovery en combinaties.

### Release Acceptance

PostgreSQL + migraties + alle P0 L2/L3/L4 + build/startup + PO-acceptatiestatus.

De huidige featuregerichte workflows blijven bestaan totdat F0-06 heeft bepaald welke evidence uniek, dubbel of obsolete is.

---

## Fase 8 — PO Acceptance Pack

Doelduur: circa **15–30 minuten**.

De PO beoordeelt primair begrijpelijkheid, logische gebruikersflow, zichtbaarheid van acties/instellingen en productmatig gewenst gedrag. PostgreSQL-, isolation-, idempotentie- en dataconsistentiechecks horen dan al automatisch groen te zijn.

---

## Fase 9 — Release Acceptance Gate

De finale gate activeert:

```text
python scripts/validate-functional-acceptance-matrix.py --strict-release
```

Een release is pas kandidaat voor PO-GO wanneer alle vereiste P0-lagen, PostgreSQL/migratie/startup en build/runtime groen zijn en de PO-acceptatiestatus expliciet is vastgelegd.

De automatisering geeft nooit zelfstandig toestemming om te mergen; expliciete PO-GO blijft vereist.
