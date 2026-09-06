# Rezzerv Integral Test Platform — Implementatiebacklog

Statusdatum: 6 september 2026
Branch: `codex/l4-06-canonical-article-identity`
Baseline: `main@e43224a74dcc0b8f7aa74bac8f636176d09360ed` (na merge PR #369 / L4-05)

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

De matrix blijft bewust conservatief. F3-03 maakt brede scenario's zoals locaties UIT, `Niet ingedeeld`, dagartikel, verbruik/correctie en alle identity-varianten niet automatisch `covered`; daarvoor blijft gerichte aanvullende L3/L4-dekking nodig.

---

## Fase 4 — P0 full-stack PostgreSQL chains — IN UITVOERING

**L4-definitie:** echte browser + echte frontend + echte backend + echte PostgreSQL. Geen `page.route(...).fulfill(...)` voor kern-API's op de normale succesroute. Kernmutaties worden via de zichtbare UI uitgevoerd; read-only API/DB-controles mogen achteraf de projectie bewijzen.

### Actuele stand op PR #370

**6 van de 7 geplande L4-authorities zijn gerealiseerd. L4-01 t/m L4-05 zijn gemerged; L4-06 is groen bewezen op de PR #370-candidate en doorloopt na de governance-update opnieuw exact-head CI.**

| ID | Keten | Status |
|---|---|---|
| L4-01 | registreren → onboarding → huishouden → instellingen → bruikbare app | **Gereed en groen** |
| L4-02 | beheerder → uitnodigen → lid accepteert → rechten → huishoudwissel → isolation | **Gereed en groen** |
| L4-03 | receipt → Kassa → goedkeuren → Uitpakken → locatie → Voorraad → historie → Bijna-op, locaties AAN | **Gereed en groen; gemerged via PR #366** |
| L4-04 | dezelfde keten met locaties UIT en zonder locatiekolom/-validatie | **Gereed en groen; gemerged via PR #368** |
| L4-05 | herverwerking/idempotentie zonder dubbele voorraad/events | **Gereed en groen; gemerged via PR #369** |
| L4-06 | aankoop → household_article → detail → historie met dezelfde canonical identity | **Gereed en groen op PR #370-authority** |
| L4-07 | platformlogin → toegestane platformfunctie → verboden huishoudactie blijft verboden | **Te bouwen — eerstvolgende L4-scope** |

### L4-01 — onboarding, locaties UIT

Authority:

- `frontend/tests/e2e/p0-onboarding.fullstack.spec.js`;
- `frontend/playwright.fullstack.config.js`;
- `.github/workflows/p0-onboarding-fullstack-postgresql-validation.yml`.

De echte browserketen bewijst:

1. accountregistratie;
2. `Wat Inhuis`;
3. aantallen aan;
4. locaties UIT;
5. Bijna-op en Winkelen aan;
6. huishouden benoemen en onboarding afronden;
7. bruikbare homeprojectie;
8. settingsprojectie met het juiste actieve profiel;
9. `Locaties` ontbreekt op home en in instellingen;
10. read-only API/session-controle op dezelfde staat.

L4-01 was groen op de finale Fase-0/1/2/3/early-F4 candidate die via PR #364 is gemerged.

### L4-02 — household membership en isolation

Authority:

- `frontend/tests/e2e/p0-household-membership.fullstack.spec.js`;
- `frontend/playwright.membership-fullstack.config.js`;
- `.github/workflows/p0-household-membership-fullstack-postgresql-validation.yml`.

De echte browserketen gebruikt twee afzonderlijke browsercontexten en bewijst:

1. beheerder en toekomstig lid hebben ieder een eigen regulier huishouden;
2. beheerder nodigt het lid uit via de zichtbare huishoudinstellingen;
3. de uitnodiging wordt via de testmailboundary daadwerkelijk afgeleverd;
4. het lid accepteert via de zichtbare uitnodigingspagina;
5. de rol in het gedeelde huishouden is `member`;
6. huishoudinstellingen zijn daar niet toegankelijk voor het lid;
7. de huishoudwisselaar schakelt tussen beide huishoudens;
8. de rol wordt per huishoudcontext correct hersteld;
9. leden-/huishouddata lekken niet tussen de twee huishoudens.

De P0 household membership full-stack PostgreSQL workflow was groen op de finale PR #364-candidate.

### L4-03 — Kassa → Uitpakken → Voorraad → Bijna-op, locaties AAN

Authority:

- `frontend/tests/e2e/p0-receipt-inventory.fullstack.spec.js`;
- `frontend/playwright.fullstack.config.js`;
- `.github/workflows/p0-receipt-inventory-fullstack-postgresql-validation.yml`;
- `backend/tests/test_live_household_article_identity_adoption.py` voor de gerichte identity-regressie die tijdens deze keten nodig bleek.

De echte browserketen bewijst:

1. registratie en onboarding met locaties AAN;
2. canonieke Jumbo-kassabon uploaden via Kassa;
3. de receipt via de zichtbare UI goedkeuren;
4. de goedgekeurde batch in Uitpakken openen;
5. een locatie via de UI creëren en selecteren;
6. één fysieke bonregel naar Voorraad verwerken;
7. dezelfde canonical `household_article_id` in Voorraad/artikeldetail gebruiken;
8. min/ideal-stock via zichtbare huishoudartikelinstellingen opslaan en na reload teruglezen;
9. vóór verbruik niet in Bijna-op;
10. via de zichtbare Afboeken-flow verbruiken;
11. daarna wel in Bijna-op;
12. browserproof en PostgreSQL-eindstaat aan dezelfde run koppelen;
13. bij eindvoorraad `0` de canonieke contractregel volgen: de lege inventory-row wordt verwijderd terwijl purchase/consume-events en household-article-identiteit de continuïteit bewijzen.

Tijdens L4-03 werd tevens het echte productdefect rond synthetische `live::...` household-article-identiteiten gevonden. PR #366 heeft de adoptie naar canonical UUID inclusief referenties in inventory/events permanent gerepareerd en regressiegeborgd.

### L4-04 — locaties UIT

PR #368 heeft de echte receipt/Uitpakken/Voorraad-keten voor een huishouden zonder locaties toegevoegd. De authority bewijst dat de locatiekolom en locatiekeuze verdwijnen, dat verwerking zonder locatie slaagt en dat locationless inventory-events geldig blijven in PostgreSQL.

### L4-05 — herverwerking/idempotentie

PR #369 heeft de dubbele/vertraagde `Naar voorraad`-grens als echte browser/PostgreSQL-authority toegevoegd. De keten bewijst dat replay hetzelfde `processed_event_id` behoudt, exact één purchase-event bestaat en de voorraad slechts één keer met `quantity_raw` stijgt.

### L4-06 — canonical article identity

Authority:

- `frontend/tests/e2e/p0-article-identity-history.fullstack.spec.js`;
- `scripts/acceptance/l4_06_article_identity_history.py`;
- `.github/workflows/p0-article-identity-history-fullstack-postgresql-validation.yml`.

De echte keten bewijst:

1. twee verschillende aankoopregels krijgen twee verschillende canonical `household_article`-UUID's;
2. beide artikelen kunnen via de echte Artikel-detail-UI dezelfde huishoudnaam krijgen zonder identity-merge;
3. de naamwijziging is na reload persistent aan dezelfde canonical identity;
4. elk Historie-scherm toont uitsluitend het eigen purchase-event;
5. purchase-import-regels, inventory en inventory-events blijven in PostgreSQL exact aan de juiste UUID gekoppeld;
6. runtime blijft DML-only;
7. de browserauthority gebruikt geen core API mocks en geen muterende `page.request`.

De reparatiecandidate `aaed274885943e2abcbdab50aff80780e697ae1f` heeft browserketen, identity-capture en exact PostgreSQL-eindbewijs volledig groen uitgevoerd. De governance-update op PR #370 wordt opnieuw op de exacte eindhead gevalideerd.

### Eerstvolgende Fase-4 stap

**L4-07 — platformlogin → toegestane platformfunctie → verboden huishoudactie blijft verboden.**

Deze laatste geplande P0-L4 authority moet de bestaande sterke F3-06 platformauthority via een echte browserreis bewijzen zonder huishoudprivilege-escalatie.

---

## Fase 5 — Historische regressiefoundation — GEDEELTELIJK OPGEBOUWD

Iedere bevestigde productbug krijgt de laagste zinvolle permanente regressietest, aanvullende L3/L4-dekking waar samenhang nodig is en een verwijzing in de matrix.

### Reeds permanent geborgd tijdens PostgreSQL- en PO-rondes

Er bestaan inmiddels gerichte regressies/gates voor meerdere defectklassen, waaronder:

- boolean/runtime-portability;
- quantity precision zonder generieke decimalenlimiet;
- receipt source/runtime wiring;
- receipt lifecycle en fail-closed gedrag;
- household location policy;
- locatievrije verwerking op gerichte lagere lagen;
- PostgreSQL household/article isolation;
- canonical household-article identity, inclusief `live::...` identity-adoptie en L4-06 same-name/rename/history-authority;
- Almost-out-projectie;
- migratie/startup en PostgreSQL zero-residual;
- brede frontendregressie.

### Nog nodig voor Fase-5-exit

De exit is nog **niet** bereikt. De volledige historische defectlijst moet systematisch worden afgevinkt tegen permanent bewijs en de Functional Acceptance Matrix, zonder impliciet krediet uit losstaande workflows.

Verplichte defectklassen blijven:

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

## Fase 6 — Failure & recovery — GEDEELTELIJK OPGEBOUWD

Er bestaat al sterk gericht bewijs voor onder meer authorization-denials, household isolation, diverse functionele foutpaden en idempotentie op lagere lagen. Dat telt als bestaande bouwsteen, maar niet als volledige Fase-6-exit.

Nog integraal af te dekken:

- 401/403 in de relevante echte gebruikersketens;
- functionele 4xx;
- gecontroleerde 5xx;
- timeout/tijdelijke fout;
- ongeldige import;
- retry/dubbele request;
- onderbroken keten;
- veilige hervatting;
- standaard gebruikersfeedback;
- databaseconsistentie na fout.

---

## Fase 7 — CI orchestration — GEDEELTELIJK OPGEBOUWD

Er bestaan veel production-relevante PostgreSQL-, L3-, L4- en regressieworkflows. De centrale orchestratie volgens de roadmap is echter nog niet gerealiseerd.

Doelstructuur:

- **PR Fast Regression:** snelle L1/L2 + relevante L3/L4.
- **Full Regression:** complete functionele regressie voor integratiekandidaat/main.
- **Deep / Nightly:** zwaardere varianten, legacydata, recovery en combinaties.
- **Release Acceptance:** PostgreSQL + migraties + alle P0 L2/L3/L4 + build/startup + PO-status.

Featuregerichte workflows worden pas geconsolideerd volgens `docs/TEST_WORKFLOW_CLASSIFICATION.md` nadat vervangend bewijs stabiel is. De bestaande workflow `test-orchestration-platform-authorization.yml` is een autorisatie-authority voor de platformroute en is **niet** de nog te bouwen overkoepelende CI-orchestrator.

---

## Fase 8 — PO Acceptance Pack — NOG TE BOUWEN

Doelduur: circa **15–30 minuten**. De PO beoordeelt primair begrijpelijkheid, logische gebruikersflow, zichtbaarheid en productmatig gewenst gedrag; technische regressie hoort al groen te zijn.

De formele, wijzigingsgerichte PO-packaging en statusregistratie zijn nog geen afgeronde platformlaag.

---

## Fase 9 — Release Acceptance Gate — VOORBEREID, NOG NIET ACTIEF

De validator ondersteunt al:

```text
python scripts/validate-functional-acceptance-matrix.py --strict-release
```

De huidige CI gebruikt voor de Functional Acceptance Matrix nog de structurele modus. `--strict-release` wordt pas de finale releasegate wanneer de resterende P0-gaten, centrale orchestratie en PO-statusregistratie gereed zijn.

Een release is pas kandidaat voor PO-GO wanneer alle vereiste P0-lagen, PostgreSQL/migratie/startup en build/runtime groen zijn en de PO-acceptatiestatus expliciet is vastgelegd. Automatisering geeft nooit zelfstandig merge-toestemming.
