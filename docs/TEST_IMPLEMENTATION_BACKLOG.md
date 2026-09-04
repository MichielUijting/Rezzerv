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
- P0 evidence-audit: **7 van 14 scenario's geverifieerd (50%)**;
- false-confidence audit: **bezig; 2 concrete patronen bevestigd**;
- P1/P2 detailaudit en workflow-consolidatie: nog open.

De 7 geverifieerde P0-scenario's zijn Account & sessie, Onboarding, Huishouden/invitations, Autorisatie & huishoudisolatie, Locatiebeleid, Kassabon → Voorraad → Bijna-op en PostgreSQL migratie/startup.

### Bevestigde false-confidence patronen

1. **SQLite onder een production-relevante workflownaam** — de bestaande Uitpakken-locatie-isolatieworkflow draait zijn kerncontract op in-memory SQLite. Dit bewijs blijft bruikbaar op L1, maar telt niet als PostgreSQL L3.
2. **Playwright + echte stack, maar cruciale API's gemockt** — de autorisatie-UI-workflow start de PostgreSQL-appstack, terwijl de Playwright-spec `/api/session` en autorisatie-endpoints met `page.route(...)` onderschept. Dit is frontendregressie, geen echte L4-keten.

| ID | Prioriteit | Werk | Status | Exitbewijs |
|---|---:|---|---|---|
| F0-01 | P0 | Centrale machineleesbare Functional Acceptance Matrix invoeren | **Gereed op branch** | `quality/acceptance/functional_acceptance_matrix.json` |
| F0-02 | P0 | Structurele validator + CI-gate invoeren | **Gereed en groen** | validator + workflow + CI-evidence |
| F0-03 | P0 | Alle huidige P0 evidence inhoudelijk verifiëren en `inventory` omzetten naar `verified` of expliciet `gap` | **Bezig — 7/14 (50%)** | alle P0-scenario's beoordeeld |
| F0-04 | P0 | Historische PO-defectklassen aan permanente scenario's koppelen | **Bezig** | locatiebeleid, quantity precision, error feedback, article history, idempotentie e.d. zichtbaar in matrix |
| F0-05 | P0 | False confidence inventariseren: mocks, alleen compilechecks, alleen HTTP-status, SQLite-approximatie, UI zonder DB-eindstaat | **Bezig — 2 patronen bevestigd** | gap-analyse per scenario |
| F0-06 | P1 | Dubbele, obsolete en PR-specifieke workflows classificeren | Open | keep/merge/retire-lijst, nog zonder ongevraagde verwijdering |
| F0-07 | P0 | Definitieve P0/P1/P2 implementatievolgorde vastleggen | Open | Fase-0 exitrapport |

### Fase-0 exit

Fase 0 is klaar wanneer alle P0-scenario's inhoudelijk zijn geverifieerd en er geen impliciete aanname meer bestaat dat een workflownaam, Docker-start of Playwright-run gelijkstaat aan integrale functionele dekking.

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

Bestaande canonical receipt-chain infrastructuur wordt waar mogelijk hergebruikt in plaats van parallel opnieuw gebouwd.

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

Volgorde:

1. **Authorization & household isolation** — omdat iedere andere keten hiervan afhankelijk is;
2. **Account/session + onboarding + household membership**;
3. **Settings/location policy** inclusief locaties uit;
4. **Kassa / Uitpakken / Voorraad / Bijna-op**;
5. **Household article identity**;
6. **Platform authority**;
7. **Migration/startup** als blijvende technische foundation.

Per P0-scenario moet L2/L3 de werkelijke eindtoestand controleren, niet alleen een HTTP- of procesexitcode.

---

## Fase 4 — P0 full-stack PostgreSQL chains

### L4-01 — Nieuwe gebruiker naar bruikbare app

`registreren -> onboarding -> huishouden -> instellingen -> bruikbare home/context`

### L4-02 — Huishouden en autorisatie

`beheerder -> uitnodigen -> lid accepteert -> rechten -> huishoudwissel -> isolation`

### L4-03 — Receipt/inventory, locaties AAN

`ZIP/EML -> Kassa -> goedkeuren -> Uitpakken -> locatie -> verwerken -> Voorraad -> historie -> Bijna-op`

### L4-04 — Receipt/inventory, locaties UIT

Dezelfde keten, maar zonder locatiekolom/-keuze en zonder foutieve locatievalidatie. Dit scenario borgt de defectklasse die tijdens de PostgreSQL PO-check naar voren kwam.

### L4-05 — Herverwerking/idempotentie

Dezelfde receipt opnieuw verwerken verandert voorraad niet dubbel en creëert geen foutieve events.

### L4-06 — Article identity/history

`aankoop -> household_article -> detail -> historie` houdt dezelfde canonieke identiteit vast.

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

Uiteindelijke centrale niveaus:

### PR Fast Regression

Snelle L1/L2 plus relevante L3/L4 op basis van geraakt scenario.

### Full Regression

Complete functionele regressie voor integratiekandidaat/main.

### Deep / Nightly

Zwaardere varianten, legacydata, recovery en combinaties.

### Release Acceptance

PostgreSQL + migraties + alle P0 L2/L3/L4 + build/startup + PO-acceptatiestatus.

De huidige featuregerichte workflows blijven bestaan totdat de audit aantoonbaar heeft bepaald welke evidence uniek, dubbel of obsolete is.

---

## Fase 8 — PO Acceptance Pack

Doelduur: circa **15–30 minuten**.

De PO beoordeelt dan primair:

- begrijpelijkheid;
- logische gebruikersflow;
- juiste zichtbaarheid van acties/instellingen;
- productmatig gewenst gedrag;
- onverwachte UX-regressies die niet zinvol volledig geautomatiseerd zijn.

Technische PostgreSQL-, isolation-, idempotentie- en dataconsistentiechecks horen vóór deze stap al groen te zijn.

---

## Fase 9 — Release Acceptance Gate

De finale gate activeert de strikte matrixcontrole:

```text
python scripts/validate-functional-acceptance-matrix.py --strict-release
```

Een release is pas kandidaat voor PO-GO wanneer:

- alle P0-scenario's hun vereiste lagen hebben;
- PostgreSQL/migratie/startup groen is;
- geen onverklaarde functionele matrix-gap resteert;
- build/runtime groen is;
- PO-acceptatiestatus expliciet is vastgelegd.

De automatisering geeft nooit zelfstandig toestemming om te mergen; de bestaande expliciete PO-GO blijft vereist.
