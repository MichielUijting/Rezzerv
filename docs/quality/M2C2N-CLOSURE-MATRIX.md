# M2C2n afsluitmatrix

Statusdatum: 2026-07-22  
Basiscommit: `b430e9cb47d4a1d4e1226992e432ce3a78722b93`

## Doel

Dit document is de enige statusbron voor de afsluiting van M2C2n: huishoudisolatie, rolgrenzen en beheer van test- en diagnostiekroutes.

Een domein krijgt pas status **GEREED** wanneer:

1. alle routes in het domein zijn geïnventariseerd;
2. per route de huishoudbron en objectbinding zijn vastgelegd;
3. lees- en schrijfrechten expliciet zijn bepaald;
4. ontbrekende grenzen zijn hersteld;
5. een gerichte contracttest bestaat;
6. alle bestaande regressie- en releasegates groen zijn;
7. resterende uitzonderingen expliciet zijn geaccepteerd of als deferred zijn geregistreerd.

`Onbekend` en `nog te inventariseren` betekenen nadrukkelijk niet dat een route veilig of onveilig is.

## Statuswaarden

- **GEREED** — volledig geïnventariseerd en bewezen tegen de eindcriteria.
- **CONTROLE** — relevante beveiliging aanwezig, maar afsluitende volledige routecontrole ontbreekt.
- **OPEN** — domein is nog niet volledig geïnventariseerd of bevat een onbewezen grens.
- **DEFERRED** — bewust buiten M2C2n geplaatst met een vastgelegde ontwerpbeslissing.

## Domeinmatrix

| ID | Domein | Huishoudisolatie | Rolgrens | Gericht bewijs | Status | Nog nodig |
|---|---|---|---|---|---|---|
| M2C2N-01 | Centrale huishoudcontext en membership | Centrale actieve huishoudcontext ingevoerd | Lidmaatschap centraal gecontroleerd | PR #160 en opvolgende regressiegates | GEREED | Geen |
| M2C2N-02 | Artikelgroepen | Objecten en queries huishoudgebonden | Mutaties volgens huishoudrol | PR #161 | GEREED | Geen |
| M2C2N-03 | Voorraadlocaties, spaces en sublocations | Inventory- en locatieobjecten aan owning household gebonden | Schrijven/adminrollen afgedwongen | PR #162 en locatie-isolatiecontract | GEREED | Geen |
| M2C2N-04 | Uitpakken: target-location | Batch- en regelhuishouden server-side afgeleid | Schrijfrecht voor mutaties | PR #164 | GEREED | Geen |
| M2C2N-05 | Uitpakken: batch/regelobjecten | Objectguard voor batch- en regelroutes | Muterende methoden vereisen schrijfrecht | PR #165 en #174 | GEREED | Geen |
| M2C2N-06 | Receipt share import | Geauthenticeerde import aan actieve huishoudcontext gebonden | Schrijfrecht afgedwongen | PR #166 | GEREED | Geen |
| M2C2N-07 | Receipt admin- en onderhoudsroutes | Geen vrije huishoudkeuze voor beheeracties | Platform-admin vereist | PR #167 en latere guarduitbreidingen; WP-1-routebaseline | CONTROLE | WP-2: alle 10 adminmutaties valideren en guard consolideren |
| M2C2N-08 | Gmail OAuth receiptbron | State en bron aan één huishouden gebonden | Geautoriseerde huishoudbeheerder | PR #168 | GEREED | Geen |
| M2C2N-09 | Resend inbound webhook en bron | Inbound bron server-side aan huishouden gebonden | Webhookcontract en broncontrole | PR #169–#171 | GEREED | Geen |
| M2C2N-10 | Purchase-import live alias backfill | Platformbeheeractie; geen vrije gebruikersscope | Platform-admin vereist | PR #172 | GEREED | Geen |
| M2C2N-11 | Receipt-exportfixtures | Vaste regressiescope | Platform-admin vereist | PR #173 | GEREED | Geen |
| M2C2N-12 | Product enrichment | Actief huishouden uit gevalideerde context | Inventory-schrijfrecht | PR #175 | GEREED | Geen |
| M2C2N-13 | Artikel-ID-verrijking en detailmutaties | Artikel binnen actieve huishoudcontext opgelost | Inventory-schrijfrecht | PR #176 | GEREED | Geen |
| M2C2N-14 | Externe productkoppeling via inventory/artikel | Inventory en household article worden binnen actief huishouden gezocht | Admin/lid, kijker geblokkeerd | Codecontrole; WP-1-routebaseline | CONTROLE | WP-3: gericht HTTP-contract toevoegen of bestaand bewijs aanwijzen |
| M2C2N-15 | Testing: store-locationdiagnostiek | Vrij `household_id` niet meer zonder beheerrecht uitvoerbaar | Platform-admin vereist | PR #177 | GEREED | Geen |
| M2C2N-16 | Testing: almost-out en inventoryfixtures | Vaste regressiescope | Platform-admin vereist | PR #178 | GEREED | Geen |
| M2C2N-17 | Overige `/api/testing/*`-routes | 40 registraties reproduceerbaar gecatalogiseerd | 17 mutaties; rolgrens nog niet volledig gevalideerd | WP-1-routebaseline | OPEN | WP-2: alle 17 testingmutaties classificeren en testen; 2 dubbele GET-registraties oplossen |
| M2C2N-18 | Product- en artikelroutes buiten reeds beschermde ingangen | Volledige routescope nu reproduceerbaar beschikbaar | Deels bewezen | PR #175/#176 en WP-1-routebaseline | CONTROLE | WP-3: domeinfilter en restcontract uitvoeren |
| M2C2N-19 | Prognoses en AlmostOut-productieroutes | Volledige routescope nu reproduceerbaar beschikbaar | Nog niet domeinbreed gevalideerd | WP-1-routebaseline | OPEN | WP-4: relevante routes uit baseline selecteren en controleren |
| M2C2N-20 | Inkoop, handmatige aankopen en importinstellingen | Volledige routescope nu reproduceerbaar beschikbaar | Deels schrijfrecht bewezen | Purchase-importguards en WP-1-routebaseline | OPEN | WP-4: productieroutes buiten batch/regelguard controleren |
| M2C2N-21 | Meldingen en notificatieconfiguratie | Volledige routescope nu reproduceerbaar beschikbaar | Nog niet domeinbreed gevalideerd | WP-1-routebaseline | OPEN | WP-5: relevante routes uit baseline selecteren en controleren |
| M2C2N-22 | Stille fallbacks `"1"` en `"demo-household"` | Routecatalogus beschikbaar; codevoorkomens nog niet geclassificeerd | Niet van toepassing | Gedeeltelijke codecontrole en WP-1-routebaseline | OPEN | WP-6: alle productievoorkomens classificeren of verwijderen |
| M2C2N-23 | `/api/receipts/share-target` | Huidige vrije `household_id` is niet eindontwerp | Toekomstig signed-tokencontract | Ontwerpbesluit vastgelegd, geen implementatie | DEFERRED | Later: kortlevend signed token, aan exact één huishouden gebonden |
| M2C2N-24 | Platform-admin-routeguard | Functioneel actief | Platform-admin | Contracttest en WP-1-routebaseline | CONTROLE | WP-2: hernoemen naar algemene guard en registratie centraliseren |

## Eindige restlijst

M2C2n bestaat vanaf dit document nog uit maximaal de volgende werkpakketten, in deze volgorde:

1. **WP-1 — Routecatalogus genereren**  
   Maak een reproduceerbare inventaris van alle FastAPI-routes met methode, pad, endpointfunctie en bronmodule. Classificeer testing/admin/productie en lees/mutatie.

2. **WP-2 — Testing en platform-admin consolideren**  
   Controleer alle `/api/testing/*`- en `/api/admin/*`-mutaties. Hernoem de huidige receipt-specifieke guard naar een algemene platform-admin-routeguard. Voeg één volledig routecontract toe.

3. **WP-3 — Producten, artikelen en externe productlinks afsluiten**  
   Sluit M2C2N-14 en M2C2N-18 met een volledige routecatalogus en gerichte HTTP-contracten.

4. **WP-4 — Prognose en inkoop afsluiten**  
   Inventariseer en herstel uitsluitend bewezen gaten in M2C2N-19 en M2C2N-20.

5. **WP-5 — Meldingen afsluiten**  
   Inventariseer huishoudscope en rolgrenzen voor meldingen en notificatieconfiguratie.

6. **WP-6 — Fallbacksanering**  
   Classificeer alle `"1"`- en `"demo-household"`-voorkomens. Productief bereikbare fallbacks worden verwijderd; bootstrap/testgevallen worden expliciet gemarkeerd.

7. **WP-7 — M2C2n eindrapport**  
   Werk alle matrixrijen bij naar GEREED of DEFERRED, voeg bewijskoppelingen toe en voer de volledige releasekwaliteitketen uit.

Er worden geen nieuwe losse beveiligings-PR’s buiten deze werkpakketten gestart.

## WP-1-uitvoer

De runtimegenerator leest de werkelijk geregistreerde `app.routes` nadat de asynchrone route-installatie stabiel is. De vaste baseline staat in `docs/quality/M2C2N-ROUTE-CATALOG-BASELINE.json` en wordt bij iedere PR opnieuw gecontroleerd.

| Kengetal | Waarde |
|---|---:|
| Routeregistraties | 196 |
| Unieke methode-padcombinaties | 194 |
| Leesregistraties | 87 |
| Mutatieregistraties | 109 |
| Production | 140 totaal / 81 muterend |
| Testing | 40 totaal / 17 muterend |
| Admin | 14 totaal / 10 muterend |
| Dev | 2 totaal / 1 muterend |
| Dubbele methode-padregistraties | 2 |

De twee dubbele registraties zijn:

- `GET /api/testing/receipt-parser-diagnosis`;
- `GET /api/testing/receipt-parser-diagnosis/download`.

## Werkpakketstatus

| Werkpakket | Status | Bewijs/uitvoer |
|---|---|---|
| WP-1 — Routecatalogus genereren | GEREED | Runtimegenerator, Docker-CI, artifact en vaste fingerprintbaseline |
| WP-2 — Testing en platform-admin consolideren | VOLGENDE | Scope: 17 testingmutaties, 10 adminmutaties en 2 dubbele GET-registraties |
| WP-3 t/m WP-7 | NIET GESTART | Wachten op afronding WP-2 |

## PR-regels vanaf nu

Iedere M2C2n-PR moet:

- exact één werkpakket noemen;
- de geraakte matrix-ID’s noemen;
- vóór de codewijziging de complete routescope tonen;
- een gericht contract toevoegen of actualiseren;
- de matrix in dezelfde PR bijwerken;
- geen status GEREED claimen zonder alle zeven eindcriteria;
- wachten op expliciete PO-GO vóór merge.

## Bewijsgrenzen

- Een groene middlewarecontracttest bewijst de geteste methode-padcombinaties, niet automatisch alle routes in een domein.
- Een gemergede PR bewijst niet zonder afzonderlijke branchcontrole dat de genoemde commit op dat moment de head van `main` is.
- Compile-, Docker- en frontendgates bewijzen regressievrij bouwen en starten, niet de volledige functionele werking van ieder scherm.
- Onbekende routes blijven OPEN totdat zij reproduceerbaar zijn geïnventariseerd.

## Afsluitcriterium M2C2n

M2C2n is pas klaar wanneer:

- M2C2N-01 t/m M2C2N-22 en M2C2N-24 op GEREED staan;
- M2C2N-23 als enige DEFERRED-rij overblijft, tenzij de PO de scope wijzigt;
- de routecatalogus geen ongeclassificeerde muterende route bevat;
- alle gerichte contracten en de volledige releasekwaliteitketen groen zijn;
- de PO expliciet GO geeft op het M2C2n-eindrapport.
