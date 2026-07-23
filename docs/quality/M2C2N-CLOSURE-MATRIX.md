# M2C2n afsluitmatrix

Statusdatum: 2026-07-22  
Basiscommit eindcontrole: `b2e5f4a89bd1a7afa9d4e2c69422bd20a5eb9840`

## Doel en eindcriteria

Dit document is de enige statusbron voor M2C2n. Een domein krijgt pas **GEREED** wanneer de routes zijn geïnventariseerd, huishoudbron en objectbinding zijn vastgelegd, rollen expliciet zijn, bewezen gaten zijn hersteld, een gericht contract bestaat en regressie- en releasegates groen zijn.

Statuswaarden: **GEREED**, **CONTROLE**, **OPEN** en **DEFERRED**. Onbekend betekent nooit impliciet veilig.

## Domeinmatrix

| ID | Domein | Huishoudisolatie | Rolgrens | Gericht bewijs | Status | Nog nodig |
|---|---|---|---|---|---|---|
| M2C2N-01 | Centrale huishoudcontext en membership | Centrale actieve huishoudcontext | Lidmaatschap centraal | PR #160 | GEREED | Geen |
| M2C2N-02 | Artikelgroepen | Huishoudgebonden | Mutaties volgens rol | PR #161 | GEREED | Geen |
| M2C2N-03 | Voorraadlocaties | Owning household | Schrijven/admin | PR #162 | GEREED | Geen |
| M2C2N-04 | Uitpakken target-location | Server-side batchscope | Schrijfrecht | PR #164 | GEREED | Geen |
| M2C2N-05 | Uitpakken batch/regel | Objectguard | Schrijfrecht | PR #165/#174 | GEREED | Geen |
| M2C2N-06 | Receipt share import | Actieve context | Schrijfrecht | PR #166 | GEREED | Geen |
| M2C2N-07 | Admin- en onderhoudsmutaties | Geen vrije gebruikersscope | Alle 10 adminmutaties centraal platform-admin | WP-2-contract | GEREED | Geen |
| M2C2N-08 | Gmail OAuth receiptbron | State en bron huishoudgebonden | Huishoudadmin | PR #168 | GEREED | Geen |
| M2C2N-09 | Resend inbound | Bron server-side huishoudgebonden | Webhookcontract | PR #169–#171 | GEREED | Geen |
| M2C2N-10 | Live-aliasbackfill | Platformbeheeractie | Platform-admin | PR #172 | GEREED | Geen |
| M2C2N-11 | Receipt-exportfixtures | Vaste regressiescope | Platform-admin | PR #173 | GEREED | Geen |
| M2C2N-12 | Product enrichment | Actieve context | Inventory-schrijfrecht | PR #175 + WP-3 | GEREED | Geen |
| M2C2N-13 | Artikel-ID-mutaties | Actieve context | Inventory-schrijfrecht | PR #176 + WP-3 | GEREED | Geen |
| M2C2N-14 | Externe productkoppeling | Actieve context of server-side inventory-eigenaar | Kijker geblokkeerd; globale mutaties platform-admin | WP-3-contract | GEREED | Geen |
| M2C2N-15 | Store-locationdiagnostiek | Vrij huishouden geblokkeerd | Platform-admin | PR #177/WP-2 | GEREED | Geen |
| M2C2N-16 | Almost-out en inventoryfixtures | Vaste regressiescope | Platform-admin | PR #178/WP-2 | GEREED | Geen |
| M2C2N-17 | Overige `/api/testing/*` | 38 registraties, 17 mutaties gecatalogiseerd | Alle 17 mutaties centraal platform-admin | WP-2-contract | GEREED | Geen |
| M2C2N-18 | Overige product- en artikelroutes | 38 routes: 14 reads en 24 mutaties | Login, inventory-schrijfrecht of platform-admin | WP-3-audit en contract | GEREED | Geen |
| M2C2N-19 | Prognoses en AlmostOut-productie | Actieve of gevalideerde huishoudcontext | Membership, huishoudadmin of platform-admin | WP-4-contract | GEREED | Geen |
| M2C2N-20 | Inkoop en importinstellingen | Owning household server-side | Membership, inventory-schrijfrecht, huishoudadmin of platform-admin | WP-4-contract | GEREED | Geen |
| M2C2N-21 | Meldingen | Actuele runtime bevat nul meldingsroutes | Geen actuele rolroute | WP-5-afwezigheidscontract | GEREED | Nieuwe implementatie vereist hercontrole |
| M2C2N-22 | Fallbacks `"1"` en `"demo-household"` | 94 runtimeverwijzingen geclassificeerd; nul ongeclassificeerd | Bestaande context- en rolgrenzen; frontend heeft geen serverautoriteit | WP-6-audit en contract | GEREED | Contract bij scopewijziging bijwerken |
| M2C2N-23 | `/api/receipts/share-target` | Vrij `household_id` is niet eindontwerp | Toekomstig signed token | Ontwerpbesluit | DEFERRED | Later afzonderlijk ontwerp |
| M2C2N-24 | Platform-admin-routeguard | Centrale expliciete routescope | Platform-admin voor 27 mutaties | Algemene guard en volledig contract | GEREED | Legacy importshim regulier opruimen |

## Routebaseline

| Kengetal | Waarde |
|---|---:|
| Routeregistraties | 194 |
| Unieke methode-padcombinaties | 194 |
| Dubbele registraties | 0 |
| Leesregistraties | 85 |
| Mutatieregistraties | 109 |
| Production | 140 totaal / 81 muterend |
| Testing | 38 totaal / 17 muterend |
| Admin | 14 totaal / 10 muterend |
| Dev | 2 totaal / 1 muterend |

De fingerprintbaseline staat in `docs/quality/M2C2N-ROUTE-CATALOG-BASELINE.json`. Iedere routewijziging moet baseline en matrix bewust bijwerken.

## Werkpakketstatus

| Werkpakket | Status | Bewijs/uitvoer |
|---|---|---|
| WP-1 — Routecatalogus | GEREED | Generator, Docker-CI en fingerprintbaseline; PR #180 |
| WP-2 — Testing en platform-admin | GEREED | Algemene guard, 27 mutaties, contract en diagnose-ontdubbeling; PR #181 |
| WP-3 — Producten en externe productlinks | GEREED | 38 routes, Docker-audit en productroutecontract; PR #182 |
| WP-4 — Prognoses en inkoop | GEREED | 23 routes en volledig dekkingscontract; PR #183 |
| WP-5 — Meldingen | GEREED | Nul actuele meldingsroutes en afwezigheidscontract; PR #184 |
| WP-6 — Fallbacks | GEREED | 94 verwijzingen geclassificeerd, nul ongeclassificeerd; PR #185 |
| WP-7 — Eindrapport | GEREED | Eindrapport en automatisch totaalcontract |

## Permanente bewaking

De gerichte workflows bewaken routecatalogus, platform-adminscope, producten, prognoses/inkoop, meldingen, fallbacks, Uitpakken, voorraadlocaties, enrichment, artikeldetail, receipt share import en de kassabonketen.

## Bewijsgrenzen

Een middlewarecontract bewijst alleen de geteste methode-padcombinaties. Groene compile-, Docker- en frontendgates bewijzen bouwen en starten, niet ieder scherm. De technische M2C2n-afsluiting is geen functionele schermacceptatie of algemene productierelease.

## Afsluitcriterium

M2C2n is technisch gereed: `M2C2N-01` t/m `M2C2N-22` en `M2C2N-24` zijn **GEREED**, `M2C2N-23` blijft als enige **DEFERRED**, geen ongeclassificeerde muterende route of huishoudfallback resteert en het WP-7-eindcontract bewaakt deze toestand. Definitieve afsluiting volgt uitsluitend na groene workflows, QA/QC en expliciete PO-GO op de WP-7-PR.
