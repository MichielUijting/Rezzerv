# M2C2n eindrapport

Statusdatum: 2026-08-03  
Basis voor eindcontrole: actuele PR-head met de gecontroleerde runtime-routebaseline.

## Eindadvies

**M2C2n eindadvies: GO** voor formele afsluiting van het huishoudisolatie- en autorisatiewerkpakket, onder behoud van precies één expliciete uitzondering: `M2C2N-23` blijft **DEFERRED**.

Dit advies betekent dat de afgesproken technische M2C2n-scope aantoonbaar is geïnventariseerd, begrensd en regressief bewaakt. Het betekent geen functionele schermacceptatie door de PO en geen algemene productierelease van Rezzerv.

## Matrixuitkomst

- `M2C2N-01` t/m `M2C2N-22`: **GEREED**.
- `M2C2N-24`: **GEREED**.
- `M2C2N-23`: als enige **DEFERRED**.
- Geen matrixonderdeel staat op **OPEN** of **CONTROLE**.

## Routebaseline

De actuele FastAPI-baseline bevat:

- 232 routeregistraties;
- 232 unieke methode-padcombinaties;
- nul dubbele registraties;
- 102 leesregistraties;
- 130 mutatieregistraties;
- 101 productiemutaties, 17 testingmutaties, 11 adminmutaties en 1 devmutatie.

De actuele routecatalogus bevat 177 productieroutes, 38 testingroutes, 15 adminroutes en 2 devroutes. Iedere routewijziging wordt door de routecatalogusworkflow en fingerprintbaseline zichtbaar gemaakt.

## Afgesloten werkpakketten

1. **WP-1 — Routecatalogus:** reproduceerbare runtimecatalogus en fingerprintbaseline.
2. **WP-2 — Testing en platform-admin:** centrale platform-adminguard voor mutaties en verwijdering van dubbele diagnoseroutes.
3. **WP-3 — Producten en externe productlinks:** huishoudisolatie, server-side objectbinding en globale catalogusrollen.
4. **WP-4 — Prognoses en inkoop:** volledige dekking van routes door bestaande context-, schrijf- en platform-admingrenzen.
5. **WP-5 — Meldingen:** twaalf expliciete supportmeldingsroutes, zonder dubbelen, met huishoud- of platformpermissieguard per route.
6. **WP-6 — Fallbacks:** relevante verwijzingen geclassificeerd en nul ongeclassificeerde huishoudfallbacks.
7. **WP-7 — Eindcontrole:** totale matrix-, baseline-, bewijs- en workflowcontrole.

## Bewijsreeks

De inhoudelijke beveiligingsreeks loopt van PR #160 tot en met PR #185. De afsluitende werkpakket-PR’s zijn:

- PR #179 — centrale afsluitmatrix;
- PR #180 — reproduceerbare routecatalogus;
- PR #181 — testing- en platform-adminconsolidatie;
- PR #182 — producten en externe productlinks;
- PR #183 — prognoses en inkoop;
- PR #184 — meldingen;
- PR #185 — huishoudfallbacks;
- WP-7 — dit eindrapport en het totale afsluitcontract.

## Enige uitgestelde uitzondering

`POST /api/receipts/share-target` blijft onder `M2C2N-23` **DEFERRED**. Het vrije `household_id` is geen geaccepteerd eindontwerp. De toekomstige oplossing moet een kortlevend, ondertekend token gebruiken dat server-side aan precies één huishouden is gebonden.

Deze uitzondering mag niet worden uitgebreid en blokkeert de formele afsluiting van de overige M2C2n-scope niet, omdat zij expliciet buiten het huidige eindcriterium is geplaatst.

## Permanente regressiebewaking

De repository bevat gerichte contracten en workflows voor:

- routecatalogus en fingerprint;
- platform-adminroutes;
- product- en artikelroutes;
- prognose-, aankoop- en importroutes;
- supportmeldingsroutes en hun autorisatieguards;
- huishoudfallbackclassificatie;
- Uitpakken-object- en locatie-isolatie;
- voorraadlocatie-isolatie;
- product enrichment en artikeldetail;
- receipt share import;
- kassabonketen en releasegates;
- huishoudleden- en autorisatie-API’s.

## Bewijsgrenzen

De eindcontrole bewijst de technische route-, huishoud-, object- en rolgrenzen binnen de vastgelegde scope. Groene Docker-, compile-, frontend- en kassabongates bewijzen bouwen, starten en de geteste ketens. Zij vervangen geen functionele schermacceptatie door de PO en bewijzen niet dat ieder toekomstig gebruiksscenario is getest.

## Formeel afsluitcriterium

M2C2n kan definitief worden afgesloten wanneer:

1. het automatische WP-7-contract groen is;
2. alle regressie- en releaseworkflows op dezelfde headcommit groen zijn;
3. QA/QC de definitieve PR-scope goedkeurt;
4. de PO expliciet GO geeft op de WP-7-PR;
5. de mergecommit daarna afzonderlijk als actuele `main`-head wordt bewezen.
