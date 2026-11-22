# PR7 — Integrale acceptatie nieuwe gebruikers en winkelhistorie

TEST_LEVEL_PROVISIONAL: M
Reden: uitsluitend contracttests (frontend/tests) en acceptatiedocumentatie; geen runtime-, schema-, CI- of versieaanpassing.

## Doel en bewijsgrens

Controleren of een nieuw regulier huishouden met minimale begeleiding vanaf registratie en winkelkoppeling naar historische aankoopgegevens, geschatte actuele beginvoorraad en Bijna op kan komen. Dit is de afsluitende gebruikersreis na PR1/#707, PR2/#708, PR3/#710, PR4/#711, PR5/#712 en PR6/#713.

**Twee strikt gescheiden bewijzen:**
1. **Automatische regressie met geïsoleerde testgegevens:** de bestaande PostgreSQL- en browserproeven en de PR7-contracttest bewaken route, toestemming, veilige winkelstatussen en prognosecontracten. Test- of mockdata bewijzen nooit dat een echte winkel alle beschikbare bonnen heeft overgedragen.
2. **Praktijkacceptatie met echte winkelaccounts:** alleen een daadwerkelijk aangemelde proefgebruiker kan aantonen welke bonnen de winkels teruggeven en of de hele reis op mobiel en desktop werkt. Leg alleen geanonimiseerde aantallen en bevindingen vast, geen accounts, tokens, kassaboninhoud of persoonsgegevens in GitHub.

Deze PR zet **geen** winkelimport- of onderhoudspauze uit, opent geen winkelaccounts, verandert geen voorraad of database, en bevat geen deployment. Het protocol is geen claim dat de praktijkproef al geslaagd is.

## Uitgangspunten voor de proef

- Gebruik een geïsoleerd, leeg **regulier testhuishouden** met expliciete toestemming van de tester. Geen bestaande gebruikersvoorraad of productiedata herschrijven.
- Registreer een nieuwe gebruiker; controleer dat deze Beheerder is van uitsluitend het eigen huishouden.
- Kies kassabonnen, Voorraad, Bijna op en Winkelen. **Waar Inhuis** en voorraadlocaties blijven aanvankelijk uit; er is geen verplichte locatie voor historische of nieuwe bonnen.
- De standaardinstelling bij het nieuwe huishouden is afboeken van oude voorraad bij een herhaalaankoop van hetzelfde bewezen artikel of bevestigde synoniemgroep. Eén herhaalaankoop (twee verschillende aankoopdagen) volstaat om een koopinterval op te slaan.
- Valideer de historie aan de hand van de originele aankoopdatum vóór de historische startgrens. Bonnen zonder betrouwbare originele datum en dubbele bonnen tellen niet als betrouwbare historische aankopen.
- Een koopinterval zonder aantoonbaar aankoopvolume geeft **geen** voorspelling met schijnzekerheid. Bijna op mag een bewaarde, ongewijzigde historische beginvoorraad gebruiken conform PR6, maar niet na een handmatige voorraadmutatie.
- Ontkoppelen, opnieuw koppelen, overslaan, afgebroken import en hervatten mogen geen dubbele bonnen of extra voorraadmutaties veroorzaken.

## Acceptatiematrix

| Stap | Verwacht gebruikersgedrag | Vereist bewijs |
| --- | --- | --- |
| A1 Registreren | Registratie en huishoudnaam, alleen/samen en functies zonder technische stappen | Bestaande P0-onboarding Playwright + praktijk |
| A2 Instellingen | Locaties uit, kassabonnen aan, standaard herhaalaankoopafboeking actief, voorspeltermijn bruikbaar | API-/PostgreSQL-controle + praktijk |
| A3 Winkelstap | AH, Lidl, Jumbo zichtbaar; overslaan toegestaan; later via Instellingen opnieuw bereikbaar | P0-browserproef + PR7-contract |
| A4 Albert Heijn | Werkelijk account verbinden, toestemming en terugkeer naar juiste Inhuis-pagina; ophalen zonder onterechte succesclaim bij importpauze | Echte accountproef; aantallen in Kassa, stopreden en eventueel tijdvenster |
| A5 Lidl | Werkelijke browseroverdracht vanuit beschikbare aankoopgeschiedenis werkt, inclusief uitleg als mobiel favoriet niet wordt ondersteund | Echte browserproef; aantallen en wachtrij, geen fictieve ingelogde status |
| A6 Jumbo | Werkelijke browserverwerking met gekozen periode werkt; onvolledige historie wordt niet als volledig aangeduid | Echte browserproef; aantallen en wachtrij |
| A7 Importvoortgang | Kassa-bonnen, historische bruikbare bonnen, wachtrij en beoordeling blijven onderscheidbaar | API-/contractproef + praktijk; geen percentage zonder winkel-totaal |
| A8 Historische beginvoorraad | Geboekte historische bonnen bepalen veilige beginvoorraad zonder verplichte locatie of handmatige beheerdersactie | Echte PostgreSQL-keten + praktijk |
| A9 Koopritme | Vanaf één herhaalaankoop wordt termijn op bewezen artikel-/synoniemidentiteit bijgewerkt, inclusief winkels door elkaar | Bestaande PR3-tests + praktijk |
| A10 Bijna op | Prognose volgt voorraad, koopritme, voorspeltermijn en ongewijzigde historische baseline; onzekere data vallen veilig terug | Bestaande PR6-/F3-tests + praktijk |
| A11 Idempotentie | Herimport en verversen verdubbelen geen bonnen, events, beginvoorraad of voorspellingen | PostgreSQL-keten + praktijk |
| A12 Veiligheid | Geen gegevens uit een ander huishouden, geen uitgeschakelde importpauze, geen client-meegegeven huishoud-ID | Bestaande autorisatie-/isolatiecontroles + praktijk |
| A13 Mobiel | Smal scherm en echte telefoon: aanmelden, winkelstap, status en Bijna op begrijpelijk en bereikbaar | Handmatige mobiel/browseracceptatie |

## Objectieve dekking van winkelhistorie

Een winkeltotaal is niet altijd bekend. Leg per winkel vast: gevraagde periode, oudste en nieuwste werkelijk ontvangen aankoopdatum, aantal duurzame bonnen in Kassa, bruikbaar voor historie, te beoordelen, in wachtrij en expliciete fouten. **Nooit '100%'** tonen of concluderen op basis van alleen opgeslagen bonnen. Voor Albert Heijn geldt de bestaande ophaalgrens van maximaal 100 bonnen per verzoek; controleer paginering of vervolgruns op aantoonbaar ontbrekende oudere perioden, zonder de importpauze te omzeilen.

Een uitgeschakelde automatische import is een **blokkade** voor volledige praktijkacceptatie, niet een reden om de pauze stilzwijgend op te heffen. Een Lidl- of Jumbo-browserfavoriet geldt niet als echte gekoppelde accountstatus; de gebruiker moet de bronactie zelf bewust uitvoeren.

## Uitvoering en besluit

1. Automatische bewijslast: `node frontend/tests/onboarding-pr7-journey.contract.mjs` (via bestaand winkelkoppelingen-contract), gerichte PR3/PR5/PR6 backendtests, de bestaande P0-onboarding fullstack, huishoudisolatie- en receipt/inventory/Bijna-op-gates.
2. Praktijkproef: A1–A13 op één testhuishouden en een apart nieuw tweede huishouden voor isolatie. Beoordeel AH, Lidl en Jumbo onafhankelijk; voer alleen winkelaccountacties uit met instemming van de eigenaar en zonder credentials in de repository.
3. Noteer per stap **Geslaagd / Niet geslaagd / Geblokkeerd / Niet uitgevoerd** en het bewijs. Een groen CI-resultaat geeft geen praktijk-GO.
4. Bij afwijking: één gerichte reparatie-PR met bijbehorend testbewijs; stel geen volledigheid voor als import of historische dekking niet objectief is aangetoond.
5. PR7 mag pas functioneel geaccepteerd worden nadat de PO de echte gebruikersreis heeft beoordeeld. Merge is afzonderlijk en expliciet; deployment/productie is een nóg afzonderlijk besluit.

## Huidig feitelijk resultaat

Het PR7-contract test uitsluitend deterministische bestaande frontendmodellen en hun onderlinge stapafhankelijkheid; de onafhankelijke PostgreSQL-/P0-suites blijven verplicht. **Echte retaileraccounts zijn in PR7 nog niet beproefd.** Geen klantlogin is in een CI-run vereist of opgeslagen.
