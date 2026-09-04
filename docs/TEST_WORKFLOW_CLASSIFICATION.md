# Rezzerv Test Workflow Classification

Statusdatum: 4 september 2026  
Roadmapfase: **Fase 0 — Test Trust Audit**  
Baseline: `main@87846e2b257cc458c24f1ea70474ab8986bfbc81`

## 1. Doel

Rezzerv heeft door opeenvolgende releases, migraties en productwijzigingen een groot aantal GitHub Actions-workflows opgebouwd. Dat is waardevol historisch bewijs, maar het aantal groene workflows mag niet langer worden verward met integrale productdekking.

Dit document classificeert de bestaande kwaliteitsgates op basis van de vraag:

> Welk uniek bewijs levert deze workflow vandaag nog, en welke plaats hoort dat bewijs in de integrale testarchitectuur te krijgen?

**Deze fase verwijdert geen workflows.** `merge-candidate` en `retire-candidate` zijn analyse-uitkomsten. Verwijdering gebeurt pas nadat het unieke bewijs aantoonbaar in de nieuwe centrale suite is overgenomen en apart is gevalideerd.

## 2. Classificaties

| Classificatie | Betekenis |
|---|---|
| **KEEP — authority** | Uniek, production-relevant bewijs; blijft voorlopig afzonderlijke kwaliteitsautoriteit. |
| **KEEP — targeted** | Waardevolle smalle regressie, maar geen integrale release-authority. |
| **MERGE-CANDIDATE** | Bewijs is nuttig maar overlapt sterk met bredere gates; later opnemen in centrale scenario-suite. |
| **RETIRE-CANDIDATE** | Historische/PR-specifieke gate waarvan de functie waarschijnlijk volledig kan worden vervangen. Eerst bewijs migreren, dan pas verwijderen. |
| **HISTORICAL EVIDENCE** | Behouden als naslag/reconstructiebewijs, niet gebruiken als actuele release-authority. |

Daarnaast staat bij sommige workflows expliciet wat zij **niet** mogen bewijzen, bijvoorbeeld `geen L3` of `geen L4`.

## 3. KEEP — actuele authority

Deze workflows leveren op dit moment aantoonbaar sterk of uniek bewijs en worden niet geconsolideerd voordat een gelijkwaardig centraal alternatief bestaat.

| Workflow | Authority | Opmerking |
|---|---|---|
| `server-side-session-security.yml` | PostgreSQL account/session L2 | Echte PostgreSQL, DML-only runtime, sessie- en accountfundament. |
| `authorization-membership-api-validation.yml` | PostgreSQL authorization API L2/L3 | Echte PostgreSQL API- en household-isolationtests. |
| `postgresql-household-invitation-authority.yml` | Invitation PostgreSQL service-authority | Migrator/runtime-scheiding en DML-only invitation lifecycle. |
| `onboarding-v2-acceptance-closure-validation.yml` | Onboarding PostgreSQL servicebaseline | Breed backendbewijs; geen echte browser-L4. |
| `inventory-location-household-isolation.yml` | Inventory/location/identity PostgreSQL service-authority | Belangrijk omdat ook household-article identity hier daadwerkelijk op PostgreSQL wordt bewezen. |
| `kassa-supermarket-baseline-validation.yml` | Kassa PostgreSQL backendbaseline | Production-like backendimage, Alembic en DML-only runtime. |
| `receipt-inventory-chain-post-merge.yml` | Canonical receipt/inventory PostgreSQL chain | 12/12 keten inclusief idempotentie en Bijna-op. |
| `postgresql-migration-foundation-validation.yml` | PostgreSQL migration authority | Canonical migration foundation. |
| `postgresql-data-migration-validation.yml` | Data-migration authority | Legacy/adoptie naar PostgreSQL. |
| `postgresql-operational-startup-validation.yml` | Operational startup authority | Production-like PostgreSQL startup. |
| `postgresql-test-infrastructure-boundary.yml` | Test datastore boundary | Voorkomt nieuw ongecontroleerd SQLite-residu. |
| `platform-admin-acceptance-closure-validation.yml` | Platform backend authority | Sterke PostgreSQL capability-/routecoverage; frontendbuild is geen L4. |
| `gpc-catalog-validation.yml` | GPC PostgreSQL service authority | Echte catalogusimport en DB/audit-eindstaat. |
| `postgresql-day-article-direct-authority.yml` | Dagartikel PostgreSQL service authority | DML-only direct-consumption semantics. |
| `support-message-api-validation.yml` | Support PostgreSQL API authority | Service/API/authorization op PostgreSQL. |
| `winkelen-frontend-regression.yml` | Winkelen mixed full-stack regression | Echte stack en echte zoekroute; mutatieflow is deels gemockt en dus slechts gedeeltelijk L4. |

## 4. KEEP — targeted regressions, maar niet als hogere laag tellen

Deze workflows blijven bruikbaar omdat zij snel een specifieke foutklasse vangen. Hun naam of testtechniek mag echter niet leiden tot een hogere L1-L4-classificatie dan zij werkelijk uitvoeren.

| Workflow | Behouden als | Niet meetellen als |
|---|---|---|
| `unpacking-household-location-isolation.yml` | SQLite isolated location contract | PostgreSQL L3 |
| `unpacking-household-object-guard.yml` | FastAPI/SQLite object-guard contract | PostgreSQL L3 |
| `unpacking-readiness-article-model-validation.yml` | Source/readiness contract | runtime L3/L4 |
| `temporal-inventory-validation.yml` | SQLite temporal/replay regression | PostgreSQL L3 |
| `settings-v2-information-architecture.yml` | Frontend settings IA/role/build contract | settings persistence L2/L3/L4 |
| `authorization-membership-ui-validation.yml` | Frontend authorization UX regression | echte L4; kern-API's worden gemockt |
| `external-recognition-confirmation-validation.yml` | Backend recognition + frontend UX contract | echte external-database L4; Playwright mockt kern-API's |
| `uitpakken-dagartikelen-release-a.yml` | Targeted backend selftest | zelfstandig PostgreSQL L3 |
| `frontend-cookie-session.yml` | Cookie/frontendsource audit + build | echte account/session L4 |
| `dynamic-home-navigation-validation.yml` | Frontend capability/navigation contract | server-side L3 |
| `dynamic-settings-validation.yml` | Frontend settings-navigation contract | settings persistence L3/L4 |

## 5. MERGE-CANDIDATES — receipt lifecycle

De receipt/kassa-keten bevat de grootste historische stapeling van losse gates. Zij worden pas geconsolideerd nadat elk uniek contract aan een matrixscenario is gekoppeld.

Primaire toekomstige authority:

- `receipt-inventory-chain-post-merge.yml` voor de canonical PostgreSQL businessketen;
- toekomstige echte L4-03/L4-04/L4-05 browserketens voor locaties AAN/UIT en idempotentie.

Te beoordelen voor samenvoeging:

- `receipt-inventory-chain-validation.yml`;
- `receipt-inventory-lifecycle.yml`;
- `receipt-lifecycle-foundation.yml`;
- `receipt-lifecycle-release-b-validation.yml`;
- `receipt-status-loyalty-local-runner-validation.yml`;
- `receipt-status-baseline-platform-authorization.yml`;
- `receipt-scanner-boundary-validation.yml`.

De household-/ingestion-boundary gates zoals Gmail, Resend, share import en webhook blijven gerichte security/integration-contracten totdat hun unieke grens expliciet is overgenomen.

## 6. MERGE-CANDIDATES — authorization & roles

De autorisatieruntime heeft meerdere historische lagen door de overgang van v1.1 naar het rollen-/accountmodel v2.0.

Primaire toekomstige authority:

- `authorization-membership-api-validation.yml` voor PostgreSQL API-authority;
- een toekomstige niet-gemockte L4-02 household/authorization chain;
- een toekomstige L4-07 platform authority.

Te beoordelen voor samenvoeging zodra die authorities volledig zijn:

- `authorization-foundation-validation.yml`;
- `authorization-membership-guards-validation.yml`;
- `authorization-matrix-acceptance.yml`;
- `authorization-disabled-ui-validation.yml`;
- `household-viewer-role-regression.yml`;
- `roles-v2-acceptance-closure.yml`;
- `superuser-foundation-validation.yml`;
- `superuser-household-readonly-validation.yml`;
- `superuser-platform-admin-stacking-cutover.yml`;
- `superuser-v2-permission-cutover.yml`.

Tot de v2.0-overgang formeel is afgerond mag historische v1.1-regressie niet stilzwijgend verdwijnen.

## 7. MERGE-CANDIDATES — platformbeheer

Er bestaan veel capability-specifieke platformworkflows. Die kunnen op termijn onder één centrale platform API-suite plus L4-07 vallen, maar alleen als hun specifieke privilegegrenzen behouden blijven.

Te beoordelen:

- `platform-audit-authorization.yml`;
- `platform-authorizations-authorization.yml`;
- `platform-background-jobs-authorization.yml`;
- `platform-feature-flags-authorization.yml`;
- `platform-integrations-authorization.yml`;
- `platform-logs-authorization.yml`;
- `platform-sessions-authorization.yml`;
- `platform-users-authorization.yml`;
- `archived-receipt-purge-platform-authorization.yml`;
- `external-relation-batch-decision-platform-authorization.yml`;
- `fixture-lifecycle-platform-authorization.yml`;
- `hybrid-regression-platform-authorization.yml`;
- `kassa-diagnostic-platform-authorization.yml`;
- `maintenance-recompute-platform-authorization.yml`;
- `technical-schema-platform-authorization.yml`;
- `test-orchestration-platform-authorization.yml`.

Classificatie: **MERGE-CANDIDATE**, niet retire-candidate. Deze gates kunnen unieke privilegegrenzen bevatten.

## 8. MERGE-CANDIDATES — support en GPC

### Support

`support-message-api-validation.yml` is de sterkste huidige PostgreSQL authority. De volgende workflows zijn kandidaat om later als gerichte cases in dezelfde API-/L4-suite te landen:

- `support-message-broadcast.yml`;
- `support-message-foundation-validation.yml`;
- `support-message-improvements.yml`;
- `support-message-role-routing.yml`;
- `support-messages-reintegration.yml`.

`support-message-documentation-contract.yml` blijft een documentatiecontract en hoeft niet noodzakelijk in runtime-CI te worden samengevoegd.

### GPC

`gpc-catalog-validation.yml` is de huidige catalogus-authority. Aanvullende GPC-workflows worden later ingedeeld in PR-fast versus deep/release, onder andere:

- `gpc-article-assignment-validation.yml`;
- `gpc-live-language-validation.yml`;
- `gpc-nl-import-platform-authorization.yml`;
- `gpc-translation-validation.yml`;
- `postgresql-gpc-residual-authority.yml`.

## 9. RETIRE-CANDIDATES — PR- of releasegebonden historie

Deze namen zijn sterk gekoppeld aan een afgesloten PR/release en zijn daardoor kandidaat om uit actieve CI te verdwijnen nadat hun unieke bewijs is gemigreerd.

| Workflow | Reden kandidaat |
|---|---|
| `pr253-full-frontend-regression.yml` | PR-specifieke volledige frontendgate. |
| `pr253-v0112109-release-package.yml` | PR-/versiespecifieke releasepackagegate. |
| `m2c2n-final-closure.yml` | Historische afsluitgate van M2C2n. |
| `m2c2n-forecast-purchase-route-audit.yml` | Historische route-audit; geen actuele PostgreSQL businessacceptatie. |
| `m2c2n-notification-route-audit.yml` | Historische route-audit. |
| `m2c2n-product-route-audit.yml` | Historische route-audit. |
| `m2c2n-product-route-guard.yml` | Historische guard uit dezelfde afsluitreeks. |

De overige M2C2n security/route-audits worden pas als retire-candidate gemarkeerd nadat is gecontroleerd dat de moderne authorization/household gates dezelfde grens daadwerkelijk afdekken.

## 10. Historische household-article Slice-workflows

De kleine Slice 2B2/2B3/2B4 workflows zijn bruikbaar als historische ontwikkelbewijsjes, maar hun naam is niet automatisch production-authority.

- `household-article-identity-slice2b2.yml` — historical/targeted;
- `household-article-identity-slice2b3.yml` — historical/targeted;
- `household-article-identity-slice2b4.yml` — historical/targeted.

Voor Slice 2B4 komt het aantoonbare PostgreSQL identity-bewijs uit `inventory-location-household-isolation.yml`, omdat die workflow de relevante test op een echte PostgreSQL 17-database uitvoert.

## 11. Consolidatieregel

Een bestaande workflow mag pas worden verwijderd wanneer **alle vier** voorwaarden waar zijn:

1. alle unieke asserts/contracten zijn geïdentificeerd;
2. zij draaien in een nieuwe of bestaande canonical authority op minstens dezelfde geldige testlaag;
3. de vervangende gate is op meerdere relevante wijzigingen aantoonbaar stabiel groen;
4. de verwijdering zelf heeft een expliciete diff- en CI-validatie.

Daarmee wordt CI-opruiming een bewijsbare migratie en geen cosmetische reductie van workflowaantallen.

## 12. Resultaat voor de roadmap

Fase 0 hoeft niet ieder historisch workflowbestand tot op de laatste regel te consolideren. De benodigde architectuurbeslissing is nu wel genomen:

- echte PostgreSQL authorities blijven leidend;
- targeted SQLite/source/frontend-contracttests blijven bruikbaar maar krijgen geen hogere status;
- overlap wordt later samengevoegd onder scenario-authorities;
- historische PR/releasegates verdwijnen pas na aantoonbare evidence-migratie;
- de Functional Acceptance Matrix bepaalt voortaan of bewijs werkelijk bijdraagt aan L1, L2, L3 of L4.
