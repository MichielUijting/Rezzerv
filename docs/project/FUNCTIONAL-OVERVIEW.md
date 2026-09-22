# Functionele hoofdprocessen

## Kassabon naar voorraad

De beoogde keten is: kassabon ontvangen, OCR en parsing, regels controleren in Kassa, koppelen aan producten of huishoudartikelen, verwerken in Uitpakken, voorraadlocatie kiezen en voorraad plus historie bijwerken. De som van de artikelen is leidend; het bon-totaal is een controlewaarde.

### Automatisch verbruik bij herhaalaankopen

Wanneer automatische afboeking voor een huishoudartikel actief is, worden meerdere aankopen van hetzelfde canonieke `household_article_id` op dezelfde kassabondatum als één cumulatieve productdag behandeld. De productdag is strikt huishoudgebonden en gebruikt de datum van de kassabon, niet de verwerkingsdatum. Daardoor kan voorraad die eerder op dezelfde dag is gekocht niet bij een tweede of later verwerkte kassabon opnieuw als oude voorraad worden afgeboekt. Een later verwerkte, maar eerder gedateerde kassabon op dezelfde kalenderdag blijft onderdeel van dezelfde productdag. Als geen bruikbare kassabondatum beschikbaar is, blijft de bestaande per-aankoopsemantiek gelden.

## Voorraad en artikelgroepen

Voorraad, locaties en artikelgroepen zijn huishoudgebonden. Artikelgroep moet zichtbaar en volgens rol wijzigbaar zijn. Beheeracties mogen alleen aan bevoegde gebruikers worden aangeboden.

## Productcatalogus en externe databases

Rezzerv scheidt centrale productkennis van huishoudartikelen en voorraad. Externe bronnen kunnen productgegevens verrijken. **Catalogus en Externe databases zijn platformbreed en gelden voor alle huishoudens.** Centrale catalogusmutaties zijn platformbeheeracties. Een huishoudspecifieke koppeling op een `household_article` is geen globale Cataloguskoppeling en mag een platformbrede externe-databasekoppeling niet blokkeren of als globale status worden geprojecteerd.

Voor bonartikelen bestaan twee geldige centrale koppelvormen:

- **Exact product:** wanneer een specifieke productidentiteit betrouwbaar bekend is, wordt gekoppeld aan een Catalogusproduct met geldige GTIN/EAN, bijpassende GTIN-identiteit en officiële GS1 GPC Brick. Een expliciete huismerkidentiteit in de bontekst (bijvoorbeeld `AH` bij Albert Heijn) blijft daarbij fail-closed: een extern exact product met conflicterend merk mag niet worden bevestigd.
- **Generiek artikel:** wanneer de kassabon het soort artikel wel betrouwbaar bepaalt maar merk, variant of GTIN niet, mag de gebruiker bewust informatieverlies accepteren en koppelen aan een generiek centraal Catalogusartikel. Dit artikel heeft een generieke naam en een officiële GS1 GPC Brick als classificatie-authority, maar **geen verplichte GTIN/EAN, merk of variant**. Voorbeeld: `AH BOUILLON` kan centraal worden gekoppeld aan `Bouillon` met de gekozen officiële Brick, zonder te doen alsof bekend is of het kip-, rund- of een andere exacte bouillonvariant was.

Automatisch zoeken blijft conservatief bij productidentiteitsconflicten. **Zelf zoeken** mag breder resultaten tonen, inclusief een zichtbaar merkconflict; zo'n conflicterend resultaat mag niet als exact product worden gekoppeld. De generieke koppeling is een aparte expliciete keuze en is niet afhankelijk van een specifieke externe productkandidaat.

Voor voorraad, Bijna op en boodschappen mag het generieke artikel leidend zijn wanneer het huishouden vooral wil weten of het artikeltype aanwezig of nodig is. Een tijdelijke of huishoudspecifieke voorkeur zoals `kip` bij `Bouillon` is geen afgeleide centrale productidentiteit; zo'n wens wordt door de gebruiker op huishoud-/boodschappenniveau vastgelegd, bijvoorbeeld in de bestaande opmerking van de boodschappenregel.

## Prognoses en Bijna op

Prognoses gebruiken huishoudgegevens en historische voorraadbewegingen. Instellingen en uitkomsten blijven aan het juiste huishouden en de juiste rol gebonden.

## Winkels en importinstellingen

Winkelkoppelingen en importinstellingen bepalen hoe aankopen en kassabonnen binnenkomen. Beheer hiervan is huishoudgebonden en voorbehouden aan de juiste beheerrol.

## Meldingen

Er bestaat op 22 juli 2026 nog geen actieve meldingen-API. Een toekomstig meldingsdomein moet eerst opnieuw worden geïnventariseerd en beveiligd.
