# M2C2n afsluitmatrix

Statusdatum: 2026-07-22  
Basiscommit: `6f6993166676d9c75be3d83452ffe95b9ba785e3`

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
| M2C2N-12 | Product enrichment | Actieve context | Inventory-schrijfrecht | PR #175 + WP-3 regressie | GEREED | Geen |
| M2C2N-13 | Artikel-ID-mutaties | Actieve context | Inventory-schrijfrecht | PR #176 + WP-3 regressie | GEREED | Geen |
| M2C2N-14 | Externe productkoppeling | Actieve huishoudcontext of server-side inventory-eigenaar; globale productcatalogus zonder vrije huishoudscope | Kijker geblokkeerd; globale catalogusmutaties platform-admin | WP-3 audit en productroutecontract | GEREED | Geen |
| M2C2N-15 | Store-locationdiagnostiek | Vrij huishouden geblokkeerd | Platform-admin | PR #177/WP-2 | GEREED | Geen |
| M2C2N-16 | Almost-out en inventoryfixtures | Vaste regressiescope | Platform-admin | PR #178/WP-2 | GEREED | Geen |
| M2C2N-17 | Overige `/api/testing/*` | 38 registraties, 17 mutaties gecatalogiseerd | Alle 17 mutaties centraal platform-admin | WP-2 volledig routecontract; geen dubbelen | GEREED | Geen |
| M2C2N-18 | Overige product- en artikelroutes | 38 routes beoordeeld: 14 reads en 24 mutaties; huishoudreads gefilterd; purchase-importmutaties via bestaande objectguard | Login voor catalogusreads; inventory-schrijfrecht voor huishoudobject; platform-admin voor globale catalogusmutaties | WP-3 Docker-audit, gericht HTTP-contract en groene regressiegates | GEREED | Geen |
| M2C2N-19 | Prognoses en AlmostOut-productie | 5 huishoudroutes gebruiken actieve of expliciet gevalideerde huishoudcontext; testingmutaties hebben geen huishoudscope | Reads vereisen membership; instellingenmutatie vereist huishoudadmin; testingmutaties platform-admin | WP-4 Docker-audit en volledig 23-routecontract | GEREED | Geen |
| M2C2N-20 | Inkoop en importinstellingen | 11 batch-/regelroutes bepalen owning household server-side; aankopen gebruiken actieve huishoudcontext; winkelimportkoppeling is huishoudadmin | Reads membership; batch-/regelmutaties inventory-schrijfrecht; importinstellingen en winkelpull huishoudadmin; adminbackfill platform-admin | WP-4 Docker-audit, bestaande Uitpakken-objectguard en volledig 23-routecontract | GEREED | Geen |
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

## WP-3 routescope en bevindingen

De reproduceerbare Docker-audit van WP-3 omvat 38 productie-registraties: 14 leesroutes en 24 mutaties.

Bewezen en hersteld:

- `GET /api/store-review-articles` vereist actieve huishoudcontext en retourneert alleen huishoudartikelen en voorraadnamen van dat actieve huishouden;
- `GET /api/inventory/groups` valideert membership van het gevraagde huishouden;
- `POST /api/inventory/items/{inventory_id}/group` bepaalt het owning household server-side en eist inventory-schrijfrecht;
- zes globale productcatalogusmutaties vereisen platform-admin;
- drie globale productcatalogusreads vereisen login;
- vier purchase-import-line-mutaties blijven afgedekt door de bestaande server-side Uitpakken-objectguard en zijn niet dubbel beveiligd.

Gericht bewijs: `backend/app/testing/product_route_household_guard_contract.py`, de Docker-auditworkflow en alle groene regressie- en releaseworkflows op de WP-3-head.

## WP-4 routescope en bevindingen

De reproduceerbare Docker-audit van WP-4 omvat 23 registraties: 6 leesroutes en 17 mutaties.

De volledige routescope valt in drie bewezen beschermingslagen:

- 11 purchase-import batch-/regelroutes worden door `unpacking_household_object_guard.py` server-side aan het owning household gebonden; reads vereisen membership en mutaties inventory-schrijfrecht;
- 3 admin/testingmutaties staan in de centrale `platform_admin_route_guard.py`;
- 9 overige routes hebben expliciete endpointcontrole: huishoudcontext, huishoudadmin, inventory-schrijfrecht of platform-admin.

Er is geen nieuw onbeveiligd productiepad bewezen. WP-4 voegt daarom geen extra productiemiddleware toe. Het gerichte contract legt de exacte 23 methode-padcombinaties, hun beschermingslaag en de read/write-afhandeling van de Uitpakken-objectguard vast.

Gericht bewijs: `backend/app/testing/forecast_purchase_route_contract.py` en `.github/workflows/m2c2n-forecast-purchase-route-audit.yml`.

## Werkpakketstatus

| Werkpakket | Status | Bewijs/uitvoer |
|---|---|---|
| WP-1 — Routecatalogus | GEREED | Generator, Docker-CI en fingerprintbaseline |
| WP-2 — Testing en platform-admin | GEREED | Algemene guard, 27 mutaties, volledig contract, diagnose-ontdubbeling; PR #181 gemerged |
| WP-3 — Producten en externe productlinks | GEREED | 38 routes, Docker-audit, productrouteguard, gericht contract en groene regressiegates; PR #182 gemerged |
| WP-4 — Prognoses en inkoop | GEREED | 23 routes, Docker-audit, drie bewezen beschermingslagen en volledig dekkingscontract |
| WP-5 — Meldingen | VOLGENDE | M2C2N-21 |
| WP-6 en WP-7 | NIET GESTART | Volgen in vastgelegde volgorde |

## PR-regels

Iedere M2C2n-PR noemt exact één werkpakket en de geraakte matrix-ID’s, toont vooraf de complete routescope, bevat een gericht contract, werkt deze matrix bij en wacht op expliciete PO-GO vóór merge.

## Bewijsgrenzen

Een middlewarecontract bewijst alleen de geteste methode-padcombinaties. Groene compile-, Docker- en frontendgates bewijzen bouwen en starten, niet ieder scherm. Een mergecommit is pas `main`-head na afzonderlijke branchvergelijking.

## Afsluitcriterium

M2C2n is pas klaar wanneer M2C2N-01 t/m M2C2N-22 en M2C2N-24 **GEREED** zijn, M2C2N-23 als enige **DEFERRED** blijft, geen ongeclassificeerde muterende route resteert, alle gerichte contracten en releasegates groen zijn en de PO expliciet GO geeft op WP-7.
