# Mobiele lijstperformance — plan en oplossingsrichting

Status: voorstel, nog zonder implementatiecode  
Doel: generiek versnellen van het laden van tabellen, reeksen en lijsten in de mobiele Inhuis-weergave.

## Probleem

De mobiele weergave gebruikt inmiddels paginering, maar de ervaren laadtijd van tabellen en reeksen is over de hele linie nog te hoog. Alleen minder regels zichtbaar maken is onvoldoende wanneer de frontend of backend vóór het tonen van pagina 1 nog steeds de volledige dataset ophaalt, verrijkt, sorteert of filtert.

Het probleem moet daarom generiek worden aangepakt op het pad van database → API → frontendrendering, in plaats van per scherm alleen cosmetische paginering toe te voegen.

## Doelstelling

De eerste mobiele pagina van een lijst of tabel moet merkbaar sneller beschikbaar zijn, zonder functionele informatie, autorisaties of huishoudisolatie te verliezen.

De voorkeursrichting is:

1. alleen de records voor de zichtbare pagina ophalen;
2. alleen de velden ophalen die voor de lijst nodig zijn;
3. zoeken, filteren en sorteren zo vroeg mogelijk uitvoeren;
4. dubbele en per-regel vervolgrequests vermijden;
5. detailinformatie pas laden wanneer de gebruiker die nodig heeft.

## Generieke oplossingsrichtingen

### 1. Echte server-side paginering

Paginering moet niet alleen bepalen hoeveel regels de frontend toont, maar ook hoeveel records de backend en database werkelijk ophalen.

Voor mobiele lijsten is de standaardrichting:
- eerste pagina met maximaal 10 records;
- API ontvangt pagina/cursor en paginagrootte;
- database retourneert alleen de benodigde records;
- totale aantallen alleen berekenen wanneer functioneel nodig.

Waar passend heeft cursor-based pagination de voorkeur boven grote OFFSET-queries bij lange datasets.

### 2. Server-side zoeken, filteren en sorteren

Zoekterm, filters en sortering worden aan de API meegegeven. De backend/PostgreSQL bepaalt de relevante subset voordat records naar de browser gaan.

Doel:
- geen volledige dataset naar de browser sturen om daar pas te filteren;
- geen grote arrays in React sorteren wanneer de database dit efficiënter kan;
- filter- en sorteercriteria blijven functioneel gelijk aan desktop.

### 3. N+1-verkeer voorkomen

Per lijst wordt onderzocht of na de hoofdrequest per regel extra requests plaatsvinden voor bijvoorbeeld:
- locatie;
- artikelgroep;
- afbeelding;
- voorraadstatus;
- koppeling/mapping;
- winkel- of boninformatie.

Waar dit voorkomt wordt gekozen voor:
- één verrijkte lijstquery;
- batch-endpoints;
- of één aanvullende batchrequest per pagina.

Nooit één netwerkrequest per zichtbare rij als dezelfde gegevens in één batch kunnen worden opgehaald.

### 4. Lijstpayload verkleinen

Een mobiele lijst krijgt alleen de velden die voor de lijstweergave nodig zijn.

Voorbeeldcategorieën:
- id;
- artikelnaam;
- hoeveelheid;
- compacte status;
- compacte locatie;
- kleine afbeeldingsreferentie.

Volledige detaildata, historie, diagnose-informatie en andere zware gegevens worden pas opgehaald bij het openen van een detailweergave.

### 5. Afbeeldingen lazy en klein laden

Product- en bonafbeeldingen mogen de eerste lijstweergave niet blokkeren.

Richting:
- lazy loading buiten de viewport;
- thumbnails voor lijsten;
- grote bronafbeelding alleen in detail/overlay;
- geen herhaalde download van dezelfde afbeelding binnen dezelfde sessie wanneer caching mogelijk is.

### 6. Databasequeries meten en gericht indexeren

Geen generieke indexen toevoegen zonder bewijs.

Per trage lijst wordt gemeten:
- queryduur;
- gebruikte filters;
- sorteerkolommen;
- joinpatronen;
- aantallen gescande versus geretourneerde records.

Alleen daarna worden passende PostgreSQL-indexen of queryaanpassingen toegevoegd, met behoud van huishoudisolatie en bestaande datacontracten.

### 7. Referentiedata cachen

Relatief stabiele gegevens hoeven niet bij iedere schermwisseling opnieuw volledig te worden geladen.

Kandidaten:
- locaties;
- sublocaties;
- artikelgroepen;
- winkels;
- andere kleine referentielijsten.

Caching mag nooit leiden tot verouderde autorisatie- of huishoudcontext. Contextgevoelige gegevens worden bij huishoudwissel of relevante mutatie ongeldig gemaakt.

### 8. Dubbele frontendrequests verwijderen

Voor elk mobiel lijstscherm wordt gecontroleerd of React-hooks, componentmounts of gedeelde providers dezelfde endpoint(s) onnodig meerdere keren aanroepen.

Doel:
- één functionele request per databron per laadmoment;
- expliciete refresh alleen na relevante mutaties;
- geen dubbele initialisatie door overlappende effects.

### 9. Volgende pagina vooraf laden

Nadat pagina 1 zichtbaar is kan de eerstvolgende pagina op de achtergrond worden voorbereid wanneer dit goedkoop en veilig is.

Voorwaarde:
- pagina 1 heeft altijd prioriteit;
- prefetch blokkeert de initiële weergave niet;
- geen overmatige dataconsumptie;
- prefetch vervalt bij gewijzigde zoekterm/filter/sortering.

### 10. Snellere ervaren rendering

Het schermframe moet direct zichtbaar worden, ook wanneer data nog onderweg is.

Richting:
- titel, acties en lijststructuur direct renderen;
- compacte skeleton/placeholder tijdens eerste fetch;
- geen volledig leeg scherm zolang de API antwoordt;
- fouten blijven via de bestaande Inhuis-meldingsroute zichtbaar.

Dit verbetert ervaren snelheid maar vervangt geen echte backend- en queryoptimalisatie.

## Eerste meetronde

Voor implementatie wordt op de belangrijkste mobiele reeksen objectief gemeten:

- Voorraad;
- Catalogus;
- Boodschappen/Winkelen;
- Kassa/Uitpakken;
- Bijna op;
- overige mobiele lijsten die dezelfde infrastructuur gebruiken.

Per scherm vastleggen:
- tijd tot eerste zichtbare regels;
- aantal API-requests;
- aantal opgehaalde records;
- responsegrootte;
- langzaamste request;
- database/queryduur waar beschikbaar;
- eventuele N+1-calls;
- dubbele requests;
- of huidige paginering frontend-only of echt server-side is.

## Voorgestelde implementatievolgorde

### Fase 1 — meten
Geen optimalisatie op aannames. Eerst per hoofdscherm de huidige laadketen vastleggen en de grootste generieke bottlenecks aanwijzen.

### Fase 2 — grootste gedeelde oorzaak oplossen
Als meerdere modules dezelfde lijstservice, hook, API-helper of queryvorm gebruiken, wordt eerst de gedeelde oorzaak aangepakt.

### Fase 3 — server-side paginering/filtering
Waar nu nog volledige datasets worden geladen, migreren naar echte backendpaginering en server-side zoek/filter/sorteerparameters.

### Fase 4 — payload en verrijking
Onnodige detailvelden uit lijstresponses halen en N+1-verrijking vervangen door batchverwerking.

### Fase 5 — databaseoptimalisatie
Alleen op basis van gemeten queries gerichte indexen/queryverbeteringen toepassen.

### Fase 6 — perceptie
Lazy images, prefetch en skeletons toevoegen nadat de echte datalaadkosten zijn teruggebracht.

## Acceptatiecriteria voor een latere implementatie

Een implementatie-PR moet per aangepakt scherm aantonen dat:
- pagina 1 niet eerst de volledige dataset nodig heeft;
- maximaal de bedoelde paginagrootte aan lijstrecords wordt opgehaald, behalve aantoonbaar noodzakelijke metadata;
- zoeken/filteren/sorteren geen volledige clientdataset vereist;
- geen N+1-patroon ontstaat;
- autorisatie en huishoudisolatie ongewijzigd correct blijven;
- desktopfunctionaliteit niet onbedoeld verslechtert;
- bestaande mobiele paginering functioneel gelijk blijft;
- de gemeten tijd tot eerste bruikbare lijst aantoonbaar verbetert ten opzichte van de baseline.

## Buiten scope van deze plan-PR

Deze PR bevat bewust geen applicatiecode en voert nog geen performance-optimalisatie uit.

Niet in deze PR:
- API-contractwijzigingen;
- frontend-hooks of componenten aanpassen;
- database-indexen toevoegen;
- querylogica wijzigen;
- caching implementeren;
- lazy loading/prefetch implementeren;
- test- of runtimeconfiguratie wijzigen.

De daadwerkelijke implementatie volgt in één of meer afzonderlijke technische PR's op basis van de meetresultaten.
