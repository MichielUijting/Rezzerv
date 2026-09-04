# Rezzerv Integral Functional Acceptance Matrix

Statusdatum: 4 september 2026  
Roadmapfase: **Fase 0 — Test Trust Audit**  
Auditbaseline: `main@87846e2b257cc458c24f1ea70474ab8986bfbc81`

## 1. Doel

Dit document is de leesbare ingang van de integrale test- en acceptatiebasis van Rezzerv. De machineleesbare bron staat in:

`quality/acceptance/functional_acceptance_matrix.json`

De centrale vraag is niet hoeveel losse workflows groen zijn, maar:

> Zijn alle productkritische gebruikersketens aantoonbaar gedekt op de juiste testlagen, tegen de juiste PostgreSQL-runtime, inclusief relevante rollen, huishoudconfiguraties, isolatie, foutpaden en herverwerking?

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

Daarnaast kent ieder scenario een auditstatus:

- **inventory** — evidence is gevonden, maar nog niet volledig inhoudelijk geverifieerd tegen het integrale scenario;
- **verified** — de evidence is tijdens deze audit inhoudelijk gecontroleerd.

**Belangrijk:** 100% `verified` betekent dat de audit compleet is, niet dat de testdekking 100% is. Een geverifieerd scenario kan bewust L2/L3/L4-gaten bevatten.

## 4. P0-audit: 14/14 geverifieerd

Alle **14 P0-scenario's zijn inhoudelijk geauditeerd (100%)**. Daardoor is nu voor ieder kritisch productgebied zichtbaar wat de bestaande automatisering werkelijk bewijst en wat nog gebouwd moet worden.

| ID | P0-domein | Audit | Belangrijkste resterende gat |
|---|---|---|---|
| P0-ACCOUNT-SESSION | Account & sessie | **verified** | Echte browsergestuurde L4-reis |
| P0-ONBOARDING | Onboarding naar bruikbare app | **verified** | Echte API/browser registratie-tot-app-keten |
| P0-HOUSEHOLD-MEMBERSHIP | Huishouden / uitnodiging / rol | **verified** | Echte API/browser uitnodigingsreis + huishoudwissel |
| P0-AUTHORIZATION-ISOLATION | Rollen en huishoudisolatie | **verified** | Niet-gemockte L4-keten |
| P0-SETTINGS-PROJECTION | Instellingen naar werkelijk gedrag | **verified** | Backendopslag + PostgreSQL + gedragsprojectie ontbreken als integrale test |
| P0-LOCATIONS-POLICY | Locaties aan/uit | **verified** | Echte PostgreSQL API + L4-configuratievarianten |
| P0-RECEIPT-INVENTORY-ALMOSTOUT | Kassa → Uitpakken → Voorraad → Bijna-op | **verified** | Echte browserketen + locaties-uit variant |
| P0-KASSA-REVIEW | Kassa review / goedkeuring | **verified** | Canonical fixture via echte UI naar PostgreSQL-eindstaat |
| P0-UNPACKING | Uitpakken / verwerken | **verified** | Echte PostgreSQL API en L4 voor alle kernvarianten |
| P0-INVENTORY | Voorraadmutaties / historie | **verified** | Echte API/browsercontrole + quantity-precisie/historie |
| P0-ALMOST-OUT | Bijna-op | **verified** | Gebruikersweergave onderdeel van dezelfde L4-keten |
| P0-ARTICLE-IDENTITY | Huishoudartikelidentiteit | **verified** | Purchase → detail → historie als echte API/browserketen |
| P0-PLATFORM-AUTHORITY | Platformrollen | **verified** | Echte browser/full-stack platformauthority |
| P0-MIGRATION-STARTUP | Migratie & startup | **verified** | Centraal combineren met functionele releaseacceptatie |

De exacte L1-L4-status en evidencepaden staan in de machineleesbare matrix.

## 5. Belangrijkste test-trust bevindingen

De audit heeft een terugkerend patroon blootgelegd: een workflownaam of technisch indrukwekkende testopzet zegt niet automatisch welke laag werkelijk wordt bewezen.

### 5.1 SQLite onder production-relevante namen

- `unpacking-household-location-isolation.yml` voert zijn kerncontract uit op `sqlite+pysqlite:///:memory:`.
- `unpacking-household-object-guard.yml` gebruikt FastAPI `TestClient`, maar ook een in-memory SQLite-engine.
- `temporal-inventory-validation.yml` test waardevolle event-/replaylogica, maar de databasegevallen zijn SQLite in-memory.

Deze tests blijven bruikbaar als L1/gerichte regressie, maar tellen niet als PostgreSQL L3.

### 5.2 Playwright met gemockte kern-API's

- `authorization-membership-ui-validation.yml` start PostgreSQL en de applicatiestack, maar de Playwright-spec mockt onder andere `/api/session` en autorisatie-endpoints met `page.route(...)`.
- receipt lifecycle/Kassa Playwright-tests mocken onder meer household-, batch-, import- en lifecycle-API's.

Dit is waardevolle frontendregressie, maar geen echte L4-keten.

### 5.3 Frontendbuild is geen full-stack acceptatie

- `settings-v2-information-architecture.yml` valideert frontendcontracten en build, maar gebruikt geen backend of PostgreSQL.
- `platform-admin-acceptance-closure-validation.yml` heeft sterke PostgreSQL backendtests en bouwt de frontend, maar voert de genoemde Playwright-platformtests niet uit.

### 5.4 Workflownaam is niet altijd het bewijs-pad

`household-article-identity-slice2b4.yml` provisiont zelf geen PostgreSQL. Het exacte identity-contract wordt echter wél betrouwbaar op PostgreSQL uitgevoerd binnen `inventory-location-household-isolation.yml`. De matrix verwijst daarom naar het werkelijke uitvoerpad.

## 6. Wat al sterk is

De audit toont ook dat er waardevolle bouwstenen aanwezig zijn:

- account/session heeft echte PostgreSQL FastAPI/API-tests voor login, 401/403, context, logout en invalidatie;
- authorization heeft echte PostgreSQL API-tests en household isolation;
- Kassa heeft een production-like PostgreSQL backendgate met Alembic en DML-only runtime;
- de canonical 12/12 receipt/inventoryketen bewijst PostgreSQL, idempotentie, voorraad `0 -> 2 -> 5 -> 5 -> 1` en Bijna-op `NEE -> JA`;
- household article identity is daadwerkelijk op PostgreSQL bewezen met `household_article_id` als anker en same-name/cross-household separation;
- platform authority heeft brede PostgreSQL capability- en routecontracten;
- migratie/startup heeft sterke migrator/runtime-scheiding en operationele PostgreSQL-gates.

Het testplatform bouwt dus voort op bestaand goed bewijs en vervangt alleen schijnzekerheid door expliciete classificatie.

## 7. P0-releaseprincipe

Een P0-scenario is niet releaseveilig enkel omdat één featuretest groen is. Voor production-relevant functioneel gedrag moeten de relevante L2-, L3- en L4-bewijzen aantoonbaar aanwezig zijn. Een technische infrastructuurketen kan L4 als `na` hebben wanneer er geen zinvolle gebruikersinterface bestaat.

De validator ondersteunt twee modi:

```text
python scripts/validate-functional-acceptance-matrix.py
```

Deze modus valideert structuur en evidence en rapporteert open P0-gaten zonder ze tijdens de opbouw als releaseblokkade te behandelen.

```text
python scripts/validate-functional-acceptance-matrix.py --strict-release
```

Deze modus maakt onopgeloste P0-dekkingsgaten blokkerend en wordt pas in roadmapfase 9 de formele releasegate.

## 8. Vaste configuratie- en regressievarianten

Minimaal de volgende varianten worden structureel onderdeel van het integrale scenario-ontwerp:

- huishouden **met locaties**;
- huishouden **zonder locaties**;
- meerdere huishoudens en expliciete household isolation;
- Beheerder en Lid plus relevante beschermde/platformrollen;
- succesvolle route, geweigerde route en foutpresentatie;
- retry/herverwerking waar mutaties idempotent moeten zijn;
- exacte niet-financiële hoeveelheden, waaronder `0.404`, `1.224` en `1.234567`;
- financiële waarden volgens hun afzonderlijke geldprecisiecontract;
- dagartikel versus fysiek voorraadartikel;
- verse PostgreSQL-database en representatieve legacy-adoptie.

## 9. PO-acceptatie

Automatisering moet bewijzen dat het product technisch en functioneel volgens de bekende contracten blijft werken. De PO beoordeelt daarna vooral of het gedrag begrijpelijk, logisch en productmatig juist is.

Een defect dat tijdens PO-acceptatie wordt gevonden volgt voortaan de vaste cyclus:

**defect → reparatie → permanente regressietest → opname in integrale matrix/suite**

Doel is een vaste handmatige PO-smoke van circa **15–30 minuten**, nadat technische regressie al automatisch groen is.

## 10. Roadmap

| Fase | Doel | Exit |
|---|---|---|
| **0 — Test Trust Audit** | Bestaande evidence en echte gaten in kaart brengen | P0 14/14 geverifieerd; P1/P2 + workflow keep/merge/retire nog afronden |
| **1 — Canonical test foundation** | Eén reproduceerbare PostgreSQL testbasis | Vaste migratie, rollen, resetbare fixtures |
| **2 — Testdata & scenario catalog** | Herbruikbare herkenbare scenario's | Canonieke huishoudens, rollen, bonnen, artikelen, legacydata |
| **3 — P0 backend/API coverage** | P0 logisch/API volledig afdekken | P0 L2/L3 geen onverklaarde gaten |
| **4 — P0 full-stack chains** | Echte frontend + backend + PostgreSQL | Kritieke gebruikersreizen L4 groen |
| **5 — Broad regression foundation** | Historische defecten permanent borgen | Relevante regressies in matrix/suite |
| **6 — Failure/recovery** | Fout- en herstelpaden bewijzen | Consistent gedrag bij fouten/retries |
| **7 — CI orchestration** | PR/full/deep gates organiseren | Eenduidige CI-uitkomst en evidence |
| **8 — PO Acceptance Pack** | Korte vaste PO-smoke | Alleen menselijke productbeoordeling over |
| **9 — Release Acceptance Gate** | Alles samenbrengen | `--strict-release` + releasebewijs groen |

## 11. Fase-0 restwerk

De **P0 Test Trust Audit is inhoudelijk afgerond**. Fase 0 als geheel sluit pas nadat ook:

1. P1/P2-domeinen voldoende zijn geïnventariseerd;
2. dubbele, obsolete en PR-specifieke workflows een `keep / merge / retire`-classificatie hebben;
3. historische PO-defectklassen aan blijvende scenario's zijn gekoppeld;
4. de definitieve implementatievolgorde voor fasen 1–4 is vastgezet.

Zie `docs/TEST_IMPLEMENTATION_BACKLOG.md` voor de uitvoering.
