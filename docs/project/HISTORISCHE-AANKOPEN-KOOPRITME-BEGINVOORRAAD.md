# PR2 — Koopritme en indicatieve beginvoorraad uit historische bonnen

Status: Draft-implementatie op afzonderlijke taakbranch. Niet activeren op de server.
TEST_LEVEL_PROVISIONAL: L (backend-API, kassabon- en voorraadgerelateerde projecties).

## PO-besluit en relatie tot PR #707

- Historische AH-, Lidl- en Jumbo-aankopen dienen als leermateriaal voor koopritme, Bijna op en een **geschatte** beginvoorraad.
- Een schatting is **nooit** bewezen fysieke voorraad, geen `inventory`-positie en geen `inventory_event`.
- De door PR1 vastgelegde huishoudgebonden datumgrens blijft leidend; oude bonnen worden niet stil in de actuele Kassa of Uitpakken teruggezet.
- Oude aankoopregels behouden hun bronidentiteit en datum; alleen betrouwbare productidentiteit en functioneel geclassificeerde productregels mogen voor schattingen tellen.
- Nieuwe bonnen blijven de gewone locatievrije verwerking volgen. `Waar Inhuis` blijft optioneel en later activeerbaar.
- Geen aannames over ontbrekende bonnetjes, volledig winkelgedrag, nulverbruik op dagen zonder aankoop of bestaande beginvoorraad.
- Alleen expliciet bevestigde product-/synoniemrelaties mogen voor aggregatie dienen. Bontekst, winkel-SKU en een suggestie zijn geen huishoudartikelidentiteit.

## Functionele contracten PR2

1. Een huishoudgebonden, read-only, gepagineerde analyse van historische aankopen met auditbare bronbonnen en waargenomen aankoopmomenten.
2. Indicatief koopritme wordt afgeleid uit herhaalde aankopen met een voldoende groot waargenomen tijdvenster. Bij te weinig bewijs of wisselende eenheden volgt `onvoldoende gegevens`, geen schijnnauwkeurige voorspelling.
3. De uitkomst kan een **onbevestigd voorstel** voor beginvoorraad per aantoonbare productidentiteit opleveren. Deze wordt uitsluitend gepresenteerd als `schatting` met bronperiode en onzekerheidsreden.
4. Zonder historische grens, bij onbetrouwbare aankoopdatum, ontbrekende voorraadgeschiktheid, ambigu of onbewezen identiteitsbewijs en duplicaten is er geen stilzwijgende voorraadinschatting.
5. Huisoudisolatie, DML-vrije GET-verwerking, geen aanmaak van `household_articles`, geen aanpassing van voorraad-/events-/kassabongegevens.
6. Geteste nul-mutaties, dubbele bonnen, grensdatum, gemengde eenheden, meerdere winkels, twee huishoudens en een te korte historie.

## Bewuste grenzen

- **Geen** automatisch boeken of definitief bevestigen van geschatte beginvoorraad.
- Geen mutatie van bestaande huishoudens of bestaande voorraad.
- Geen nieuwe account-/retailerlogin, importer, herimport of locatie-aanmaak.
- De uiteindelijke onboardinggebruiksinterface en expliciete voorraadcorrectie worden afzonderlijk geactiveerd na toetsbare gebruikersbevestiging.
- De bestaande Bijna op-voorraadwaarheid blijft onveranderd; PR2 levert apart leermateriaal, geen vervangende voorraadprojectie.

## Kwaliteitsvolgorde

Gerichte unit/integratietests eerst, daarna normaal CI, versie 1.12.432 (na implementatie synchroniseren), preflight, Ready, F7 Full exact-candidate op definitieve SHA, functionele PO-acceptatie. Geen merge of deployment zonder afzonderlijke expliciete PO-GO.
