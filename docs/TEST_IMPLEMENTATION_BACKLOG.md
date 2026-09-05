# Rezzerv Integral Test Platform — Implementatiebacklog

Statusdatum: 4 september 2026
Branch: `codex/integral-test-foundation-phase-0`
Baseline: `main@87846e2b257cc458c24f1ea70474ab8986bfbc81`

## Doel

Deze backlog vertaalt `docs/TEST_MATRIX.md` naar concrete bouwstappen. Prioriteit wordt bepaald door productrisico en ketenimpact, niet door het aantal bestaande tests.

---

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

| Patroon | Werkelijke betekenis |
|---|---|
| SQLite onder production-relevante workflownaam | Gericht L1/L2-bewijs; geen PostgreSQL L3 |
| FastAPI TestClient maar SQLite | API-contract; geen production-like L3 |
| Database-regressie op SQLite | Waardevolle logica; geen PostgreSQL-runtimebewijs |
| Playwright + echte stack maar kern-API's gemockt | Frontendregressie; geen echte L4 |
| Frontendcontract/build zonder backend | UI-structuur; geen opslaan → DB → gedragsprojectie |
| Workflownaam zonder self-contained PostgreSQL | Bewijs telt alleen waar het werkelijk uitvoert |

---

## Fase 1 — Canonical PostgreSQL test foundation — AFGEROND

**Doel:** integrale tests reproduceerbaar laten starten op dezelfde production-like databasegrens.

De gedeelde foundation staat in:

- `backend/app/testing/postgresql_acceptance_foundation.py`;
- `.github/actions/postgresql-acceptance-foundation/action.yml`;
- `backend/app/testing/canonical_acceptance_foundation.py`;
- `.github/workflows/canonical-acceptance-foundation-validation.yml`.

| ID | Prioriteit | Werk | Status |
|---|---:|---|---|
| F1-01 | P0 | Eén geïsoleerde PostgreSQL 17 foundation | **Gereed en groen** |
| F1-02 | P0 | Migrator + DML-only runtime-role | **Gereed en groen** |
| F1-03 | P0 | Canonical Alembic-head als startvoorwaarde | **Gereed en groen** |
| F1-04 | P0 | Deterministische reset/reseed | **Gereed en groen** |
| F1-05 | P0 | Run identity/evidence | **Gereed en groen** |
| F1-06 | P0 | Bestaande goede PG fixtures achter één gedeelde interface | **Gereed en groen** |

### Canonical huishoudscenario's

1. `acceptance-locations-on` — regulier huishouden, Beheerder + Lid, `waar_inhuis`, exact één hoofdlocatie en één sublocatie.
2. `acceptance-locations-off` — regulier huishouden, Beheerder + Lid, `wat_inhuis`, exact nul locaties.
3. `acceptance-isolation` — tweede regulier huishouden, Beheerder + Lid, exact nul locaties en geen leakage.

De receipt-keten blijft aantoonbaar PostgreSQL/DML-only en bewijst voorraadpad **0 → 2 → 5 → 5 → 1**, idempotentie, Bijna-op **NEE → JA** en geweigerde runtime-DDL. De expliciete historische locationless SQLite-contracttest blijft `sqlite-test-only` en telt niet als production evidence.

---

## Fase 2 — Testdata en scenario catalog — AFGEROND

**Doel:** vaste productherkenbare scenario's die door L2, L3 en L4 worden gedeeld, met één stabiele catalogus in plaats van losse fixture-eilanden.

### Centrale authority

- `quality/acceptance/canonical_scenario_catalog.json`;
- `backend/app/testing/canonical_scenario_catalog.py`;
- `.github/workflows/canonical-acceptance-foundation-validation.yml`.

### Canonical fixturegroepen

- huishoudcontexten: locaties AAN, locaties UIT, isolation en systeemhuishouden `0` uitsluitend voor expliciete systeem/legacycontracten;
- kassabonnen: normale fysieke receipt, loyaliteitsregel, weighted `0.404 kg`, onzekere reviewregel;
- artikelen: bestaand, nieuw, `Niet ingedeeld`, dagartikel;
- quantities exact: `0.404`, `1.224`, `1.234567`;
- financiële waarden apart: EUR, schaal 2;
- Bijna-op minimum 5 met 6/5/4/0 grensgevallen;
- synthetische legacy-adoptiedata met exact quantity-behoud.

| ID | Prioriteit | Werk | Status |
|---|---:|---|---|
| F2-01 | P0 | Canonical huishoudcontexten | **Gereed** |
| F2-02 | P0 | Productherkenbare receipt-fixtures | **Gereed** |
| F2-03 | P0 | Article-fixtures incl. dagartikel en `Niet ingedeeld` | **Gereed** |
| F2-04 | P0 | Quantity- en financieel precisiecontract | **Gereed** |
| F2-05 | P0 | Bijna-op + synthetische legacydata | **Gereed** |
| F2-06 | P0 | Cross-layer loader/validator + CI-evidence | **Gereed en groen** |

Fase 2 bewijst de testdata en scenariosemantiek; gedrag wordt in Fase 3 en 4 bewezen.

---

## Fase 3 — P0 backend/API coverage — AFGEROND

**Exitcriterium:** de geplande F3-authorities draaien via echte API/runtime op PostgreSQL, controleren de database-eindtoestand waar relevant en overstaten brede varianten niet als gedekt.

| ID | Prioriteit | Authority | Status | Bewijs |
|---|---:|---|---|---|
| F3-01 | P0 | Settings + location policy | **Gereed en groen** | `backend/tests/settings_location_policy_api_selftest.py`; `circular-capability-expansion-validation.yml` |
| F3-02 | P0 | Onboarding + household membership | **Gereed en groen** | `backend/tests/onboarding_household_membership_api_selftest.py`; `onboarding-household-membership-api-validation.yml` |
| F3-03 | P0 | Uitpakken + inventory + article identity | **Gereed en groen als gerichte L3-slice** | `backend/tests/unpacking_inventory_article_identity_api_selftest.py`; `unpacking-inventory-article-identity-api-validation.yml` |
| F3-04 | P0 | Kassa review/approval | **Gereed en groen** | `backend/tests/kassa_review_api_selftest.py`; `kassa-review-api-validation.yml` |
| F3-05 | P0 | Almost-out API/projectie | **Gereed en groen** | `backend/tests/almost_out_api_projection_selftest.py`; `almost-out-api-projection-validation.yml` |
| F3-06 | P0 | Platform authority | **Gereed en groen** | `backend/tests/platform_authority_api_selftest.py`; `platform-authority-api-validation.yml` |
| F3-07 | P0 | Account/session + authorization authorities behouden | **Bestaand groen** | server-session en authorization PostgreSQL authorities |
| F3-08 | P0 | Migration/startup authorities behouden | **Bestaand groen** | PostgreSQL migration/startup gates |

### Fase-3 eindbewijs

Candidate `3210cc59cb9ae3c404552b53a35bf4ddfcaf3e49` is volledig groen over de complete PR-CI-golf, inclusief:

- F3-01 t/m F3-06;
- canonical foundation en Functional Acceptance Matrix validation;
- PostgreSQL migration/test-infrastructure/zero-residual gates;
- receipt inventory chain;
- volledige frontend regression.

De matrix is bewust conservatief bijgewerkt. F3-03 maakt brede scenario's zoals locaties UIT, `Niet ingedeeld`, dagartikel, verbruik/correctie en alle identity-varianten niet automatisch `covered`; daarvoor blijft gerichte aanvullende L3/L4-dekking nodig.

---

## Fase 4 — P0 full-stack PostgreSQL chains — IN UITVOERING

**L4-definitie:** echte browser + echte frontend + echte backend + echte PostgreSQL. Geen `page.route(...).fulfill(...)` voor kern-API's op de normale succesroute. Kernmutaties worden via de zichtbare UI uitgevoerd; read-only API/DB-controles mogen achteraf de projectie bewijzen.

| ID | Keten | Status |
|---|---|---|
| L4-01 | registreren → onboarding → huishouden → instellingen → bruikbare app | **Implementatie toegevoegd; CI-bewijs volgt op opvolgcandidate** |
| L4-02 | beheerder → uitnodigen → lid accepteert → rechten → huishoudwissel → isolation | Te bouwen |
| L4-03 | receipt → Kassa → goedkeuren → Uitpakken → locatie → Voorraad → historie → Bijna-op, locaties AAN | Te bouwen |
| L4-04 | dezelfde keten met locaties UIT en zonder locatiekolom/-validatie | Te bouwen |
| L4-05 | herverwerking/idempotentie zonder dubbele voorraad/events | Te bouwen |
| L4-06 | aankoop → household_article → detail → historie met dezelfde canonical identity | Te bouwen |
| L4-07 | platformlogin → toegestane platformfunctie → verboden huishoudactie blijft verboden | Te bouwen |

### L4-01 implementatiecontract

Nieuw:

- `frontend/tests/e2e/p0-onboarding.fullstack.spec.js`;
- `frontend/playwright.fullstack.config.js`;
- `.github/workflows/p0-onboarding-fullstack-postgresql-validation.yml`.

De keten doet via de echte browser-UI:

1. account registreren;
2. `Wat Inhuis` kiezen;
3. aantallen aanzetten;
4. locaties expliciet UIT laten;
5. Bijna-op en Winkelen aanzetten;
6. huishouden benoemen en onboarding afronden;
7. bruikbare home- en settingsprojectie controleren;
8. vervolgens read-only API-projectie en directe PostgreSQL-eindstaat controleren.

De workflow faalt statisch wanneer de L4-spec `page.route()` of muterende `page.request.post/put/patch/delete` gebruikt voor de kernflow.

---

## Fase 5 — Historische regressiefoundation

Iedere bevestigde productbug krijgt de laagste zinvolle permanente regressietest, aanvullende L3/L4-dekking waar samenhang nodig is en een verwijzing in de matrix.

Verplichte defectklassen uit de PostgreSQL PO-ronde:

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
