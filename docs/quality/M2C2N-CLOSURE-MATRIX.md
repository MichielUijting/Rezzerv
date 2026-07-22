# M2C2n afsluitmatrix

Statusdatum: 2026-07-22  
Basiscommit: `846b0e42c2c7b58e37de9017be4942dbc6300c41`

## Doel en eindcriteria

Dit document is de enige statusbron voor M2C2n. Een domein krijgt pas **GEREED** wanneer alle routes zijn geïnventariseerd, huishoudbron en objectbinding zijn vastgelegd, rollen expliciet zijn, bewezen gaten zijn hersteld, een gericht contract bestaat, alle regressie- en releasegates groen zijn en uitzonderingen expliciet zijn geaccepteerd of uitgesteld.

Statuswaarden: **GEREED**, **CONTROLE**, **OPEN** en **DEFERRED**. Onbekend betekent nooit impliciet veilig of onveilig.

## Domeinmatrix

| ID | Domein | Huishoudisolatie | Rolgrens | Gericht bewijs | Status | Nog nodig |
|---|---|---|---|---|---|---|
| M2C2N-01 | Centrale huishoudcontext en membership | Centrale actieve huishoudcontext | Lidmaatschap centraal | PR #160 | GEREED | Geen |
| M2C2N-02 | Artikelgroepen | Huishoudgebonden | Mutaties volgens rol | PR #161 | GEREED | Geen |
| M2C2N-03 | Voorraadlocaties | Owning household | Schrijven/admin | PR #162 | GEREED | Geen |
| M2C2N-04 | Uitpakken target-location | Server-side batchscope | Schrijfrecht | PR #164 | GEREED | Geen |
| M2C2N-05 | Uitpakken batch/regel | Objectguard | Schrijfrecht | PR #165/#174 | GEREED | Geen |
| M2C2N-06 | Receipt share import | Actieve context | Schrijfrecht | PR #166 | GEREED | Geen |
| M2C2N-07 | Admin- en onderhoudsmutaties | Geen vrije gebruikersscope | Alle 10 adminmutaties centraal platform-admin | WP-2 volledig routecontract | GEREED | Geen |
| M2C2N-08 | Gmail OAuth receiptbron | State en bron huishoudgebonden | Huishoudadmin | PR #168 | GEREED | Geen |
| M2C2N-09 | Resend inbound | Bron server-side huishoudgebonden | Webhookcontract | PR #169–#171 | GEREED | Geen |
| M2C2N-10 | Live-aliasbackfill | Platformbeheeractie | Platform-admin | PR #172 | GEREED | Geen |
| M2C2N-11 | Receipt-exportfixtures | Vaste regressiescope | Platform-admin | PR #173 | GEREED | Geen |
| M2C2N-12 | Product enrichment | Actieve context | Inventory-schrijfrecht | PR #175 | GEREED | Geen |
| M2C2N-13 | Artikel-ID-mutaties | Actieve context | Inventory-schrijfrecht | PR #176 | GEREED | Geen |
| M2C2N-14 | Externe productkoppeling | Objecten binnen actief huishouden | Kijker geblokkeerd | WP-1-baseline | CONTROLE | WP-3-contract |
| M2C2N-15 | Store-locationdiagnostiek | Vrij huishouden geblokkeerd | Platform-admin | PR #177/WP-2 | GEREED | Geen |
| M2C2N-16 | Almost-out en inventoryfixtures | Vaste regressiescope | Platform-admin | PR #178/WP-2 | GEREED | Geen |
| M2C2N-17 | Overige `/api/testing/*` | 38 registraties, 17 mutaties gecatalogiseerd | Alle 17 mutaties centraal platform-admin | WP-2 volledig routecontract; geen dubbelen | GEREED | Geen |
| M2C2N-18 | Overige product- en artikelroutes | Volledige routescope beschikbaar | Deels bewezen | WP-1 | CONTROLE | WP-3 |
| M2C2N-19 | Prognoses en AlmostOut-productie | Routescope beschikbaar | Nog niet domeinbreed | WP-1 | OPEN | WP-4 |
| M2C2N-20 | Inkoop en importinstellingen | Routescope beschikbaar | Deels bewezen | WP-1 | OPEN | WP-4 |
| M2C2N-21 | Meldingen | Routescope beschikbaar | Nog niet domeinbreed | WP-1 | OPEN | WP-5 |
| M2C2N-22 | Fallbacks `"1"` en `"demo-household"` | Nog te classificeren | n.v.t. | WP-1 | OPEN | WP-6 |
| M2C2N-23 | `/api/receipts/share-target` | Vrij `household_id` is niet eindontwerp | Toekomstig signed token | Ontwerpbesluit | DEFERRED | Later apart ontwerp |
| M2C2N-24 | Platform-admin-routeguard | Centrale expliciete routescope | Platform-admin voor 27 mutaties | Algemene guard en volledig contract | GEREED | Legacy importshim later regulier opruimen |

## WP-1-routebaseline na WP-2

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

De baseline staat in `docs/quality/M2C2N-ROUTE-CATALOG-BASELINE.json`. Iedere routewijziging moet deze baseline en matrix bewust bijwerken.

## Werkpakketstatus

| Werkpakket | Status | Bewijs/uitvoer |
|---|---|---|
| WP-1 — Routecatalogus | GEREED | Generator, Docker-CI en fingerprintbaseline |
| WP-2 — Testing en platform-admin | IN REVIEW | Algemene guard, 27 mutaties, volledig contract, diagnose-ontdubbeling |
| WP-3 — Producten en externe productlinks | VOLGENDE | M2C2N-14 en M2C2N-18 |
| WP-4 t/m WP-7 | NIET GESTART | Volgen in vastgelegde volgorde |

## PR-regels

Iedere M2C2n-PR noemt exact één werkpakket en de geraakte matrix-ID’s, toont vooraf de complete routescope, bevat een gericht contract, werkt deze matrix bij en wacht op expliciete PO-GO vóór merge.

## Bewijsgrenzen

Een middlewarecontract bewijst alleen de geteste methode-padcombinaties. Groene compile-, Docker- en frontendgates bewijzen bouwen en starten, niet ieder scherm. Een mergecommit is pas `main`-head na afzonderlijke branchvergelijking.

## Afsluitcriterium

M2C2n is pas klaar wanneer M2C2N-01 t/m M2C2N-22 en M2C2N-24 **GEREED** zijn, M2C2N-23 als enige **DEFERRED** blijft, geen ongeclassificeerde muterende route resteert, alle gerichte contracten en releasegates groen zijn en de PO expliciet GO geeft op WP-7.
