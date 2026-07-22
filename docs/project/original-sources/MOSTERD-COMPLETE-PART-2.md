# Volledige broninhoud — Mosterd, deel 2 van 2

Bronbestand: `Mosterd.docx`

- Kunnen de gevraagde producten bij mij worden afgeleverd?

  - Picnic, Gorilla

- Wat zijn de Nutriscores of (totaal)calorieën van mijn inkopen van de
  afgelopen periode?

  - YAZIO, Mijn Leefstijlcoach, Lifesum, WeightWatchers, Fatsecret

- Welke aanbiedingen zijn er voor mijn verwachte inkoop voor de komende
  2 weken?

  - Alle aangesloten winkels

- Verlengen of beëindigen van abonnementen

  - Alle artikelen van type abonnement

Op basis van de consument van de bezittingen kunnen service leveranciers
allerlei diensten aanbieden. Denk hierbij aan verzekeraars,
energieleveranciers, servicemonteurs, bedrijven als Picnic, et cetera.
Het is denkbaar dat er volledig nieuwe services ‘ontstaan’ omdat
ondernemers beter kunnen inspelen op consumentenbehoeften. Een
businessmodel voor de consument is om je data te verkopen. Dat is een
mogelijkheid maar roept ook weer veel bedenkingen op. Daar ga ik nu niet
verder op in.

<u>Privacybewakers</u>

- De consument bepaalt welke gegevens van hem/haar worden verstrekt aan
  wie.

- Welke instanties hebben welke gegevens van de gebruiker ontvangen.

- Welke instanties ontvangen welke gegevens van de gebruiker.

- Opdrachten geven tot verwijderen van privacygevoelige data

- Startpunt is dat er geen data van de gebruiker beschikbaar worden
  gesteld, tenzij uitdrukkelijk aangegeven door de gebruiker.

- Kunnen resetten naar de startpunt-instellingen.

<u>Concurrentie en substituten</u>

- Nielsen: vooral dienstbaar aan de business en niet de consument.

- Klantenkaarten van winkelketens.

- Vergelijkbare Apps als Rezzerv maar zonder links naar de
  winkel(keten)s. KitchenPal, All my Stuff.

<u>Ontwikkeling van de Rezzerv-App</u>

1.  Fase 1: initiatie

    1.  Opstellen prototype tbv fundwerving en eerste contacten winkels

    2.  Opstellen businessplan t.b.v. fundwerving

    3.  Funding voor fase 1 t/m 4

    4.  Opbouwen ontwikkelstraat, technische architectuur en development
        stack

    5.  Definiëren en bouwen MVP (webservice en app), zonder interfaces
        met externe partijen

    6.  Testen MVP met testgroep

2.  Fase 2: Connectie

    1.  Business case voor de winkelketen opstellen

    2.  Basiscontract winkels opstellen

    3.  Contracteren eerste winkelketen

    4.  Test koppeling met eerste winkelketen

    5.  Contracteren volgende winkelketens

    6.  Testen koppelingen met volgende winkelketens

3.  Fase 3: Première

    1.  Basiscontract consument opstellen

    2.  Ontwerp App-functionaliteiten en usability

    3.  Bepalen première-backlog

    4.  Ontwikkelen Première-versie

    5.  Testen Première-versie met testgroep en winkelketens

    6.  Aanmelden in App-store en Google Play (Android)

    7.  Opstellen marketingplan

4.  Go live

    1.  Inrichten servicelijnen stakeholders

    2.  Ondersteuningsteam winkelketens aanstellen en instrueren

    3.  Devops-team aanstellen en instrueren

    4.  Dashboards gebruik, service en incidenten opbouwen en
        operationeel maken

    5.  Start marketingacties

5.  Uitbouw

    1.  Uitbouw aansluiting winkelketens

    2.  Vervolg marketingacties

    3.  Uitbouw aansluiting service leveranciers

<u>Go to market (welke aanpak om tot een implementatie van Rezzerv te
komen)</u>

De Go to market versie is hetgeen in fase 3c wordt opgesteld. Ik hanteer
3 uitgangspunten voor de go to market versie:

1.  First time right. Als de eerste ervaring niet overtuigend is, dan
    wordt de App direct verwijderd door de gebruiker. Er is weinig kans
    dat er nog een tweede kans komt en de mond-op-mond-reclame wordt in
    de kiem gesmoord.

2.  Je hoeft geen moeite te doen voor de bijhouding van je bezittingen.
    Als je er wel moeite voor gaat doen, dan zal de meerwaarde wel sterk
    stijgen.

3.  Overtuigende toegevoegde waarde. Er zullen relevante inzichten
    geboden moeten worden in de eerste versie.

Om te bepalen wat voldoende is zal er een referentiegroep worden
samengesteld. Dat moet een afspiegeling zijn van de maatschappij omdat
op voorhand nog geen segmentering wordt toegepast. Bij te snelle
segmentering kan er tunnelvisie ontstaan. Bij te late segmentering heb
je kans dat je overvraagd wordt qua functionaliteit en snelheid gaat
verliezen. Dit is wat mij betreft nog een punt van nader onderzoek.

<u>Het businessmodel van Rezzerv (hoe wordt Rezzerv gefinancierd,
initieel en structureel)</u>

Het belang van de consument staat centraal. Eerste optie is
crowd-funding met een terugbetalingsregeling met hoog rendement.

Naast de (initiële) crowd funding wil ik enkele licentiemodellen
toevoegen:

- Jaarlijkse bijdrage van service leveranciers: Exciting licentie. Dit
  zal mede afhankelijk zijn van de service leveranciers zelf. Eerste
  insteek is om de service leveranciers te laten betalen voor het
  Rezzerv-platform en niet de consumenten.

- Abonnementen van consumenten voor specifieke smart services: Smart
  licentie

- Jaarlijkse bijdragen van winkelketens voor verstrekte consumentendata:
  Easy licentie

<u>Applicatie-architectuur en basiscomponenten</u>

In onderstaand schema zijn de softwarecomponenten. Deze componenten
hebben een App-versie en een webservice-versie. De ontwikkelomvang van
de webservice is veel omvangrijker dan de App.

Per softwarecomponent heb ik beknopt aangegeven wat de
hoofdfunctionaliteiten zijn.

<u>Database</u>

1.  Gebruiker

2.  Huishouden

3.  Bezittingen

4.  Artikelen

5.  Afnemers

6.  Leveranciers

7.  Services

8.  Overzichten

9.  Overzichtmappen

10. Logging

Openstaande vragen:

- Wat is minimaal nodig om de App te lanceren?

- Wat zijn aansprekende inzichten en services zijn te maken op basis van
  de beschikbare data?

- Welke winkel(keten) als eerste benaderen?

- In hoeverre is een alliantie met de consumentenbond te overwegen?

- Welke winkelketen is het meest kansrijk om als eerste in te stappen

- Wat is de omvang van de App om te kunnen lanceren en de uitgebreide
  versie?

- Hoe crowd funding zonder alles prijs te geven? En wat wordt de
  tegenprestatie?

- Wie wil het Rezzerv-team aansturen?

- Welke externe funding aanboren? En wat wordt de tegenprestatie?

- Welke concurrenten zijn er en welke is de meest ‘kansrijke’?

User interface.

1.  Login / aanmaken account

2.  Landingspagina:

    1.  Menu-items

    2.  Mijn bezittingen per categorie.

<!-- -->

1.  Testen van het idee: lost het een probleem op en past het bij het
    gedrag van mensen?

2.  Maak schetsen

3.  Use cases: wat moet de app ondersteunen

4.  Lelijke digitale prototype

5.  Zorg voor een communicatietool: om de ideeën te delen

6.  Mooie digitale prototype

7.
