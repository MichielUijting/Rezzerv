# Functionele hoofdprocessen

## Kassabon naar voorraad

De beoogde keten is: kassabon ontvangen, OCR en parsing, regels controleren in Kassa, koppelen aan producten of huishoudartikelen en daarna verwerken naar Voorraad. **Uitpakken is alleen een tussenstap wanneer locatie-toewijzing daadwerkelijk actief is.** Als Uitpakken/Waar Inhuis niet actief is, gaat een goedgekeurde gewone voorraadregel rechtstreeks naar Voorraad met een echte locatievrije opslag (`space_id=NULL`, `sublocation_id=NULL`); de systeemterm **Direct** is daarbij geen voorraadlocatie en wordt niet als locatie geprojecteerd. Een artikel met afhandeling `DIRECT_CONSUMPTION` blijft daarvan strikt gescheiden: aankoop/consumptie wordt geregistreerd, maar er ontstaat geen voorraadmutatie. De som van de artikelen is leidend; het bon-totaal is een controlewaarde.

### Automatisch verbruik bij herhaalaankopen

Wanneer automatische afboeking voor een huishoudartikel actief is, worden meerdere aankopen van hetzelfde canonieke `household_article_id` op dezelfde kassabondatum als één cumulatieve productdag behandeld. De productdag is strikt huishoudgebonden en gebruikt de datum van de kassabon, niet de verwerkingsdatum. Daardoor kan voorraad die eerder op dezelfde dag is gekocht niet bij een tweede of later verwerkte kassabon opnieuw als oude voorraad worden afgeboekt. Een later verwerkte, maar eerder gedateerde kassabon op dezelfde kalenderdag blijft onderdeel van dezelfde productdag. Als geen bruikbare kassabondatum beschikbaar is, blijft de bestaande per-aankoopsemantiek gelden.

## Voorraad en artikelgroepen

Voorraad, locaties en artikelgroepen zijn huishoudgebonden. Artikelgroep moet zichtbaar en volgens rol wijzigbaar zijn. Beheeracties mogen alleen aan bevoegde gebruikers worden aangeboden.

## Productcatalogus en externe databases

Rezzerv scheidt centrale productkennis van huishoudartikelen en voorraad. Externe bronnen kunnen productgegevens verrijken. **Catalogus en Externe databases zijn platformbreed en gelden voor alle huishoudens.** Centrale catalogusmutaties zijn platformbeheeracties. Een huishoudspecifieke koppeling op een `household_article` is geen globale Cataloguskoppeling en mag een platformbrede externe-databasekoppeling niet blokkeren of als globale status worden geprojecteerd.

Voor bonartikelen bestaan twee geldige centrale koppelvormen:

- **Exact product:** wanneer een specifieke productidentiteit betrouwbaar bekend is, wordt gekoppeld aan een Catalogusproduct met geldige GTIN/EAN, bijpassende GTIN-identiteit en officiële GS1 GPC Brick. Een expliciete huismerkidentiteit in de bontekst (bijvoorbeeld `AH` bij Albert Heijn) blijft daarbij fail-closed: een extern exact product met conflicterend merk mag niet worden bevestigd.
- **Generiek artikel:** wanneer de kassabon het soort artikel wel betrouwbaar bepaalt maar merk, variant of GTIN niet, mag de gebruiker bewust informatieverlies accepteren en koppelen aan een generiek centraal Catalogusartikel. Dit artikel heeft een generieke naam en een officiële GS1 GPC Brick als classificatie-authority, maar **geen verplichte GTIN/EAN, merk of variant**. Voorbeeld: `AH BOUILLON` kan centraal worden gekoppeld aan `Bouillon` met de gekozen officiële Brick, zonder te doen alsof bekend is of het kip-, rund- of een andere exacte bouillonvariant was.

Productfoto's uit betrouwbare enrichment worden centraal op het Catalogusproduct opgeslagen en daarna geprojecteerd naar gekoppelde huishoudartikelen en Voorraad. Een bestaande niet-lege Catalogusfoto wordt niet automatisch door een externe bron overschreven. Bij runtime-start worden ontbrekende Catalogusfoto's terugwerkend aangevuld uit reeds opgeslagen succesvolle enrichment-data; aansluitend wordt de bestaande representatieve Voorraadfoto-backfill uitgevoerd. Producten waarvoor geen bron ooit een afbeelding heeft geleverd blijven zonder foto totdat een bron later wel een afbeelding levert of een bevoegde gebruiker handmatig een Catalogusfoto vastlegt.

De mobiele Incidentele aankoop start scanner-first: bij openen probeert Inhuis direct de barcodescanner te starten. De browser blijft de autoriteit voor cameratoestemming. De scanner kan worden geannuleerd; daarna blijft de gebruiker op Incidentele aankoop en kan de barcode handmatig worden ingevuld.

Na een gescande of handmatig ingevulde barcode verschijnen **Controleren** en **Naar voorraad** naast elkaar. **Controleren** voert de exacte GTIN-lookup uit, vult beschikbare productgegevens inclusief productfoto aan en schrijft het centrale Catalogusproduct bij. Deze Catalogusstap staat functioneel los van Voorraad: een gebruiker mag na Controleren stoppen zonder het product in Voorraad op te nemen. Als geen externe bron een bruikbare naam levert, kan de gebruiker de artikelnaam handmatig invullen; die naam kan via Controleren als centrale Catalogusnaam worden vastgelegd zolang geen betrouwbaardere bronmatch de productnaam levert.

**Naar voorraad** wordt pas actief nadat de actuele barcode is gecontroleerd. Die actie toont alleen de gegevens die nodig zijn om het artikel in Voorraad te plaatsen, primair Locatie en Sublocatie. Aantal 1 en de huidige aankoopdatum blijven standaardwaarden; winkel, prijs en notitie staan onder Meer gegevens. **Annuleren** in deze Voorraadstap beëindigt de Voorraadopname zonder de al uitgevoerde Cataloguscontrole of Catalogusopname terug te draaien.

Voor mobiele barcodescans probeert Inhuis eerst de reguliere achtercamera (environment) op hoge resolutie, met continue autofocus waar het apparaat dit ondersteunt. Digitale zoom wordt niet automatisch geforceerd omdat dit barcodes onscherper kan maken. Daarna blijft de native BarcodeDetector -> ZXing fallback actief. Bij een geweigerde of geblokkeerde browsertoestemming toont Inhuis foutfeedback en valt de gebruiker terug op handmatige invoer.

Exacte GTIN-zoekopdrachten gebruiken één gedeelde bronketen voor Incidentele aankoop en Externe databases. De keten probeert eerst bestaande centrale Cataloguskennis en daarna geconfigureerde openbare productbronnen. Een externe match wordt alleen als exact product gebruikt wanneer dezelfde GTIN op een concrete productpagina of productrespons samen met een bruikbare productnaam wordt aangetroffen. Een bronhit mag in Externe databases read-only als kandidaat worden getoond; pas een expliciete of domeinspecifiek toegestane opslagstap mag centrale Catalogus- of huishoudkoppelingen maken. Open Food Facts en MyRealFood zijn actuele openbare GTIN-bronnen; lokale referentie- en geconfigureerde GS1-bronnen blijven daarna beschikbaar voor de incidentele-aankoopverrijking.

Automatisch zoeken blijft conservatief bij productidentiteitsconflicten. **Zelf zoeken** mag breder resultaten tonen, inclusief een zichtbaar merkconflict; zo'n conflicterend resultaat mag niet als exact product worden gekoppeld. De generieke koppeling is een aparte expliciete keuze en is niet afhankelijk van een specifieke externe productkandidaat.

Voor voorraad, Bijna op en boodschappen mag het generieke artikel leidend zijn wanneer het huishouden vooral wil weten of het artikeltype aanwezig of nodig is. Een tijdelijke of huishoudspecifieke voorkeur zoals `kip` bij `Bouillon` is geen afgeleide centrale productidentiteit; zo'n wens wordt door de gebruiker op huishoud-/boodschappenniveau vastgelegd, bijvoorbeeld in de bestaande opmerking van de boodschappenregel.

## Prognoses en Bijna op

Prognoses gebruiken huishoudgegevens en historische voorraadbewegingen. Instellingen en uitkomsten blijven aan het juiste huishouden en de juiste rol gebonden.

## Winkels en importinstellingen

Winkelkoppelingen en importinstellingen bepalen hoe aankopen en kassabonnen binnenkomen. Beheer hiervan is huishoudgebonden en voorbehouden aan de juiste beheerrol.

## Meldingen

Er bestaat op 22 juli 2026 nog geen actieve meldingen-API. Een toekomstig meldingsdomein moet eerst opnieuw worden geïnventariseerd en beveiligd.
