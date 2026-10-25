# Herstel van dubbele gewichtsregels

De Lidl-bronnormalisatie herkent een losse `gewicht x kiloprijs`-regel vóór
Kassa/Uitpakken. Samenvoegen vereist hetzelfde winkelartikelnummer, aansluitende
regels en overeenkomende hoeveelheid, prijs en bedrag. Tegenstrijdige of losse
details krijgen `unknown`, zijn niet voorraadgerechtigd en vragen controle.
Gewone herhaalde aankopen blijven afzonderlijke artikelen.

Externe databases 2 gebruikt alleen actieve productregels van niet-verwijderde
bonnen. De leesroute gebruikt de opgeslagen regelrol en voorraadgerechtigdheid;
zij leidt geen nieuwe artikelidentiteit af uit een naam. De weergavenaam is de
genormaliseerde artikelnaam en het bonartikelnummer is de winkelcode.

## Bestaande gegevens

`app.maintenance.repair_weight_detail_rows` biedt een expliciet herstelplan en
een afzonderlijke toepassing. Dit draait nooit automatisch bij opstarten.
Het Windows-herstelscript bewaart eerst een JSON-veiligheidskopie in Downloads.
Daarna controleert een transactie opnieuw alle bewijsgegevens en de planhash.
Bij verschil stopt het gehele herstel zonder wijzigingen.

Alleen niet-goedgekeurde bonnen met een bewezen dubbele detailregel komen in
aanmerking. De detailregel mag geen artikel-, catalogus- of kandidaatkoppeling
hebben. Het herstel markeert alleen die bronregel als verwijderd en metadata,
met voorraadgerechtigdheid 0. Ruwe bontekst en het echte artikel blijven bewaard.
Catalogus, huishoudartikelen, bedragen en voorraad worden niet gewijzigd.
Een tweede uitvoering hoort nul nieuwe wijzigingen op te leveren.

De ontvangen databaseanalyse toonde 15 dergelijke regels op verwijderde bonnen,
geen overeenkomstige vervuiling in Catalogus of voorraad. Goedgekeurde of
gekoppelde regels worden bewust niet op basis van tekst verwijderd.

## Aanvullend: verkeerd gemarkeerd statiegeld

`app.maintenance.repair_legacy_deposit_rows` corrigeert oude productrollen voor
statiegeld/emballage. Zowel ruwe als genormaliseerde brontekst moeten volgens de
bestaande bronclassificatie statiegeld aantonen en er moet een regelbedrag zijn.
Een tegenstrijdige artikelnaam wordt niet overschreven. Alleen de opgeslagen
rol wordt financieel en voorraadgerechtigdheid wordt 0. De regel wordt niet
verwijderd; bedrag, labels, bestaande koppelingen en voorraadgeschiedenis blijven
behouden, ook op een eerder goedgekeurde bon. Er wordt geen voorraadcorrectie
of Catalogusopschoning op basis van een naam uitgevoerd.

Een onverwerkte zelfstandige aankoopimport is een productcollectie, geen financieel
grootboek. Een daarin toegelaten statiegeldregel kan expliciet worden verwijderd
na een volledige bronveiligheidskopie, uitsluitend zonder verwerkingsfeit,
verwerkingstijdstip, product-/huishoudkoppeling of externe kandidaat. De originele
batchbron blijft behouden. Gekoppelde/verwerkte gevallen worden niet verwijderd.

Het aparte artikel-herstel-CMD combineert beide expliciete plannen in één
veiligheidskopie en transactie. Het normale test/startscript blijft uitsluitend
de bestaande opstartroute gebruiken. Eerst software starten, daarna het afzonderlijke
herstelscript uitvoeren en de lijst verversen. Een tweede herstelrun moet 0 wijzigen.

## Controle

1. Start de nieuwe PR-versie via het bijgewerkte testscript en `start.bat`.
2. Controleer Externe databases 2: verwijderde bonnen, koopzegels en losse
   gewichtsdetails horen niet als artikelen in de lijst.
3. Importeer een Lidl-bon met een gewogen artikel. In Kassa/Uitpakken staat het
   artikel eenmaal, met het juiste gewicht en bedrag. Een onzekere detailregel
   vraagt controle en mag geen voorraadartikel opleveren.
4. Voer het afzonderlijke herstelscript uit. Bewaar rapport en veiligheidskopie.
   Voer het nogmaals uit: het aantal herstelde regels hoort dan nul te zijn.

Automatische bewijzen: bronnormalisatie en conservatieve herstelunit-tests;
de PostgreSQL DML-authority controleert de echte leesquery, het herstel en het
behoud van het artikel in een teruggedraaide testtransactie.
