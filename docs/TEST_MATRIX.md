# Rezzerv Integral Functional Acceptance Matrix

Statusdatum: 4 september 2026  
Roadmapfase: **Fase 0 — Test Trust Audit**  
Auditbaseline: `main@87846e2b257cc458c24f1ea70474ab8986bfbc81`

## 1. Doel

Dit document is de leesbare ingang van de integrale test- en acceptatiebasis van Rezzerv. De machineleesbare bron staat in:

`quality/acceptance/functional_acceptance_matrix.json`

De centrale vraag is niet meer hoeveel losse workflows groen zijn, maar:

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

Deze scheiding voorkomt dat het bestaan van een workflow automatisch als functionele dekking wordt geïnterpreteerd.

## 4. Huidige kernbevindingen

Rezzerv heeft al veel regressie- en acceptatiechecks. De huidige kwaliteitssignalen zijn echter historisch gegroeid en verdeeld over veel feature-, release- en migratiegerichte workflows. Daardoor kan een groot aantal groene workflows nog steeds samengaan met een gat in een complete gebruikersketen.

In deze eerste audit zijn inmiddels vier P0-gebieden inhoudelijk gecontroleerd:

1. **Account & sessie** heeft sterk PostgreSQL L2/L3-bewijs. `backend/tests/test_server_session_routes.py` gebruikt een echte FastAPI `TestClient` met PostgreSQL en controleert onder andere login, 401/403, sessiecontext, logout en invalidatie. De ontbrekende laag is de echte browsergestuurde L4-reis.
2. **Locatiebeleid** bevat sterk PostgreSQL service/isolation-bewijs, maar de bestaande workflow `unpacking-household-location-isolation.yml` voert zijn Uitpakken-locatiecontract uit op **in-memory SQLite**. Dit telt daarom niet als PostgreSQL L3-bewijs. API- en L4-dekking voor locaties aan/uit blijven open.
3. **Kassabon → Voorraad → Bijna-op** heeft een canonical PostgreSQL 12/12 ketenrunner met DML-only runtime, idempotentie, voorraadpad `0 -> 2 -> 5 -> 5 -> 1` en Bijna-op `NEE -> JA`. De browsergestuurde L4-keten ontbreekt nog.
4. **PostgreSQL migratie/startup** heeft expliciete migrator/runtime-scheiding en operationele startupgates.

Dit bevestigt de kernwaarde van de matrix: de naam van een workflow is geen bewijs van de laag, datastore of gebruikersketen die hij werkelijk test.

## 5. Eerste integrale scenario-inventaris

| ID | Domein / keten | Prioriteit | Audit | Belangrijkste resterende gat |
|---|---|---:|---|---|
| P0-ACCOUNT-SESSION | Account & sessie | P0 | **verified** | Echte browsergestuurde L4-reis |
| P0-ONBOARDING | Onboarding naar bruikbare app | P0 | inventory | Browsergestuurde registratie-tot-app-keten |
| P0-HOUSEHOLD-MEMBERSHIP | Huishouden / uitnodiging / rol | P0 | inventory | UI + runtime + huishoudwissel integraal |
| P0-AUTHORIZATION-ISOLATION | Rollen en huishoudisolatie | P0 | inventory | 190-check runtime en v2.0 doelcontract zichtbaar koppelen |
| P0-SETTINGS-PROJECTION | Instellingen naar werkelijk gedrag | P0 | inventory | Cross-layer instellingseffecten |
| P0-LOCATIONS-POLICY | Locaties aan/uit | P0 | **verified** | Echte API + L4; bestaand Uitpakken-contract is SQLite-only |
| P0-RECEIPT-INVENTORY-ALMOSTOUT | Kassa → Uitpakken → Voorraad → Bijna-op | P0 | **verified** | Echte browserketen + locaties-uit variant |
| P0-KASSA-REVIEW | Kassa review / goedkeuring | P0 | inventory | UI aan canonical fixture en DB-eindstaat koppelen |
| P0-UNPACKING | Uitpakken / verwerken | P0 | inventory | Losse varianten onder één ketenautoriteit brengen |
| P0-INVENTORY | Voorraadmutaties / historie | P0 | inventory | Browsercontrole + exact quantity-contract |
| P0-ALMOST-OUT | Bijna-op | P0 | inventory | Gebruikersweergave onderdeel van L4-keten |
| P1-SHOPPING | Winkelen | P1 | inventory | Frontendbewijs koppelen aan backend/DB-eindstaat |
| P0-ARTICLE-IDENTITY | Huishoudartikelidentiteit | P0 | inventory | Purchase-to-history identiteit integraal bewijzen |
| P1-GPC-ARTICLE-GROUP | GPC en Artikelgroepen | P1 | inventory | Centrale en huishoudspecifieke verantwoordelijkheid samen bewijzen |
| P1-DAY-ARTICLE | Dagartikelen | P1 | inventory | Echte browserketen |
| P1-SUPPORT-MESSAGES | Support / berichten | P1 | inventory | Actuele workflows exact koppelen aan scenario |
| P0-PLATFORM-AUTHORITY | Platformrollen | P0 | inventory | Runtime-v1.1 en doel-v2.0 expliciet scheiden/testen |
| P0-MIGRATION-STARTUP | Migratie & startup | P0 | **verified** | Opnemen in één integrale release acceptance gate |

De details en evidencepaden staan uitsluitend in de machineleesbare matrix om dubbele administraties te voorkomen.

## 6. P0-releaseprincipe

Een P0-scenario is niet releaseveilig enkel omdat één featuretest groen is. Voor production-relevant functioneel gedrag moeten de relevante L2-, L3- en L4-bewijzen aantoonbaar aanwezig zijn. Een technische infrastructuurketen kan L4 als `na` hebben wanneer er geen zinvolle gebruikersinterface bestaat.

De validator ondersteunt daarom twee modi:

```text
python scripts/validate-functional-acceptance-matrix.py
```

Controleert de structuur, toegestane labels, evidence bij `covered`, P0/PostgreSQL-contracten en rapporteert open gaten. Deze modus is tijdens de opbouw de CI-gate.

```text
python scripts/validate-functional-acceptance-matrix.py --strict-release
```

Maakt onopgeloste P0-dekkingsgaten blokkerend. Deze modus wordt pas de formele releasegate wanneer roadmapfase 9 is bereikt.

## 7. Vaste configuratie- en regressievarianten

Minimaal de volgende varianten worden niet langer als incidentele bugtest behandeld, maar als onderdeel van het integrale scenario-ontwerp:

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

## 8. PO-acceptatie

Automatisering moet bewijzen dat het product technisch en functioneel volgens de bekende contracten blijft werken. De PO beoordeelt daarna vooral of het gedrag begrijpelijk, logisch en productmatig juist is.

Een defect dat tijdens PO-acceptatie wordt gevonden volgt voortaan de vaste cyclus:

**defect → reparatie → permanente regressietest → opname in integrale matrix/suite**

Daarmee wordt de handmatige PO-smoke uiteindelijk kort en doelgericht in plaats van een vervanging voor ontbrekende regressieautomatisering.

## 9. Roadmap

| Fase | Doel | Exit |
|---|---|---|
| **0 — Test Trust Audit** | Bestaande evidence en echte gaten volledig in kaart brengen | Definitieve matrix + gap-analyse + P0/P1/P2 backlog |
| **1 — Canonical test foundation** | Eén reproduceerbare PostgreSQL testbasis | Vaste migratie, rollen, resetbare fixtures |
| **2 — Testdata & scenario catalog** | Herbruikbare herkenbare scenario's | Canonieke huishoudens, rollen, bonnen, artikelen, legacydata |
| **3 — P0 backend/API coverage** | P0 logisch/API volledig afdekken | P0 L2/L3 geen onverklaarde gaten |
| **4 — P0 full-stack chains** | Echte frontend + backend + PostgreSQL | Kritieke gebruikersreizen L4 groen |
| **5 — Broad regression foundation** | Historische defecten permanent borgen | Relevante regressies in matrix/suite |
| **6 — Failure/recovery** | Fout- en herstelpaden bewijzen | Consistent gedrag bij fouten/retries |
| **7 — CI orchestration** | PR/full/deep gates organiseren | Eenduidige CI-uitkomst en evidence |
| **8 — PO Acceptance Pack** | Korte vaste PO-smoke | Alleen menselijke productbeoordeling over |
| **9 — Release Acceptance Gate** | Alles samenbrengen | `--strict-release` + releasebewijs groen |

## 10. Huidige fase-exit

Fase 0 is pas klaar wanneer:

1. alle P0/P1/P2 functionele domeinen aantoonbaar zijn geïnventariseerd;
2. alle relevante bestaande tests/workflows inhoudelijk aan L1-L4 zijn gekoppeld;
3. `inventory` voor P0 is teruggebracht naar `verified` of een expliciet `gap`;
4. false-positive tests of dubbele/obsolete gates zijn benoemd;
5. de concrete implementatiebacklog is geprioriteerd;
6. geen bestaand groen signaal als méér bewijs wordt gepresenteerd dan het werkelijk levert.

Zie `docs/TEST_IMPLEMENTATION_BACKLOG.md` voor de concrete uitvoeringsvolgorde.
