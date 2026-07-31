# M2C2n afsluitmatrix

Statusdatum: 2026-07-31  
Basiscommit eindcontrole: actuele PR-head van PR #214.

## Doel en eindcriteria

Dit document is de centrale statusbron voor M2C2n. Een domein krijgt pas **GEREED** wanneer de routes zijn geïnventariseerd, huishoudbron en objectbinding zijn vastgelegd, rollen expliciet zijn, bewezen gaten zijn hersteld, een gericht contract bestaat en regressie- en vrijgavecontroles groen zijn.

Statuswaarden: **GEREED**, **CONTROLE**, **OPEN** en **DEFERRED**. Onbekend betekent nooit impliciet veilig.

## Domeinmatrix

| ID | Domein | Huishoudisolatie | Rolgrens | Gericht bewijs | Status | Nog nodig |
|---|---|---|---|---|---|---|
| M2C2N-01 | Centrale huishoudcontext en lidmaatschap | Centrale actieve huishoudcontext | Lidmaatschap centraal | PR #160 + autorisatiecontracten | GEREED | Geen |
| M2C2N-02 | Artikelgroepen | Huishoudgebonden | Mutaties volgens rol | PR #161 | GEREED | Geen |
| M2C2N-03 | Voorraadlocaties | Eigenaarshuishouden | Schrijfrecht | PR #162 | GEREED | Geen |
| M2C2N-04 | Uitpakken doellocatie | Server-side batchscope | Schrijfrecht | PR #164 | GEREED | Geen |
| M2C2N-05 | Uitpakken batch/regel | Objectguard | Schrijfrecht | PR #165/#174 | GEREED | Geen |
| M2C2N-06 | Gedeelde kassabonimport | Actieve context | Schrijfrecht | PR #166 | GEREED | Geen |
| M2C2N-07 | Centrale onderhoudsmutaties | Geen vrije gebruikersscope | Centrale platformbevoegdheid | WP-2-contract | GEREED | Geen |
| M2C2N-08 | Gmail OAuth-kassabonbron | State en bron huishoudgebonden | Eigenaar | PR #168 | GEREED | Geen |
| M2C2N-09 | Resend inbound | Bron server-side huishoudgebonden | Webhookcontract | PR #169–#171 | GEREED | Geen |
| M2C2N-10 | Live-aliasbackfill | Platformbeheeractie | Centrale platformbevoegdheid | PR #172 | GEREED | Geen |
| M2C2N-11 | Kassabon-exportfixtures | Vaste regressiescope | Centrale platformbevoegdheid | PR #173 | GEREED | Geen |
| M2C2N-12 | Productverrijking | Actieve context | Voorraadschrijfrecht | PR #175 + WP-3 | GEREED | Geen |
| M2C2N-13 | Artikel-ID-mutaties | Actieve context | Voorraadschrijfrecht | PR #176 + WP-3 | GEREED | Geen |
| M2C2N-14 | Externe productkoppeling | Actieve context of server-side voorraadeigenaar | Kijker geblokkeerd; globale mutaties centraal | WP-3-contract | GEREED | Geen |
| M2C2N-15 | Winkellocatiediagnostiek | Vrij huishouden geblokkeerd | Centrale platformbevoegdheid | PR #177/WP-2 | GEREED | Geen |
| M2C2N-16 | Bijna-op- en voorraadfixtures | Vaste regressiescope | Centrale platformbevoegdheid | PR #178/WP-2 | GEREED | Geen |
| M2C2N-17 | Overige `/api/testing/*` | 38 registraties, 17 mutaties gecatalogiseerd | Alle 17 mutaties centraal beveiligd | WP-2-contract | GEREED | Geen |
| M2C2N-18 | Overige product- en artikelroutes | Routefamilie gecatalogiseerd | Login, voorraadschrijfrecht of centrale platformbevoegdheid | WP-3-audit en contract | GEREED | Geen |
| M2C2N-19 | Prognoses en Bijna-op-productie | Actieve of gevalideerde huishoudcontext | Lidmaatschap, Eigenaar of centrale platformbevoegdheid | WP-4-contract | GEREED | Geen |
| M2C2N-20 | Inkoop en importinstellingen | Eigenaarshuishouden server-side | Lidmaatschap, voorraadschrijfrecht, Eigenaar of centrale platformbevoegdheid | WP-4-contract | GEREED | Geen |
| M2C2N-21 | Meldingen | Huishoudroutes server-side gebonden; centrale routes afzonderlijk beveiligd | Eigenaar/Lid voor huishouden; Supergebruiker onbeperkt; Frontteam huishouden 0 plus eigen lidmaatschappen | Meldingen-API-, frontend-, scope- en routecontracten | GEREED | Geen |
| M2C2N-22 | Fallbacks `"1"` en `"demo-household"` | Runtimeverwijzingen geclassificeerd; nul ongeclassificeerd | Bestaande context- en rolgrenzen; frontend heeft geen serverautoriteit | WP-6-audit en contract | GEREED | Contract bij scopewijziging bijwerken |
| M2C2N-23 | `/api/receipts/share-target` | Vrij `household_id` is niet eindontwerp | Toekomstig ondertekend token | Ontwerpbesluit | DEFERRED | Later afzonderlijk ontwerp |
| M2C2N-24 | Centrale platformrouteguard | Centrale expliciete routescope | Centrale rol- en bevoegdheidscontrole | Algemene guard en volledig contract | GEREED | Oude compatibiliteitsnamen regulier opruimen |

## Routebaseline

| Kengetal | Waarde |
|---|---:|
| Routeregistraties | 229 |
| Unieke methode-padcombinaties | 229 |
| Dubbele registraties | 0 |
| Leesregistraties | 103 |
| Mutatieregistraties | 126 |
| Productie | 174 totaal / 97 muterend |
| Testing | 38 totaal / 17 muterend |
| Admin | 15 totaal / 11 muterend |
| Dev | 2 totaal / 1 muterend |

De fingerprintbaseline staat in `docs/quality/M2C2N-ROUTE-CATALOG-BASELINE.json`. Iedere routewijziging moet baseline en matrix bewust bijwerken.

## Werkpakketstatus

| Werkpakket | Status | Bewijs/uitvoer |
|---|---|---|
| WP-1 — Routecatalogus | GEREED | Generator, CI en fingerprintbaseline |
| WP-2 — Testing en platformbeveiliging | GEREED | Algemene guard, contracten en diagnose-ontdubbeling |
| WP-3 — Producten en externe productlinks | GEREED | Route-audit en productroutecontract |
| WP-4 — Prognoses en inkoop | GEREED | Volledig dekkingscontract |
| WP-5 — Meldingen | GEREED | Huishoud- en centrale routes, autorisatie-, scope- en frontendcontracten |
| WP-6 — Fallbacks | GEREED | Verwijzingen geclassificeerd, nul ongeclassificeerd |
| WP-7 — Eindrapport | GEREED | Eindrapport en automatisch totaalcontract |

## Permanente bewaking

De gerichte workflows bewaken routecatalogus, platformroutes, producten, prognoses/inkoop, Meldingen, fallbacks, Uitpakken, voorraadlocaties, productverrijking, artikeldetail, gedeelde kassabonimport, autorisatie en de kassabonketen.

## Bewijsgrenzen

Een middlewarecontract bewijst alleen de geteste methode-padcombinaties. Groene compile-, Docker- en frontendcontroles bewijzen bouwen en starten, niet ieder scherm. De technische M2C2n-afsluiting is geen functionele schermacceptatie of algemene productierelease.

## Afsluitcriterium

M2C2n is technisch gereed wanneer `M2C2N-01` t/m `M2C2N-22` en `M2C2N-24` **GEREED** zijn, `M2C2N-23` als enige **DEFERRED** blijft, geen ongeclassificeerde muterende route of huishoudfallback resteert en het WP-7-eindcontract deze toestand bewaakt. Definitieve afsluiting volgt uitsluitend na groene workflows, QA/QC en expliciete PO-GO.
