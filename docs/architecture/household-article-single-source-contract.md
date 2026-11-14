# Huishoudartikel als enige functionele artikelbron

Status: bindend contract voor Uitpakken, Artikelgroepen en Voorraad.

## Kernregel

`household_articles.id` (`household_article_id`) is de enige functionele identiteit voor een artikel binnen een huishouden.

De zichtbare begrippen **Mijn artikel** in Uitpakken en **Voorraadartikel** in Voorraad zijn geen afzonderlijke domeinentiteiten. Het zijn twee schermcontexten van hetzelfde huishoudartikel.

## Relaties

- Een kassabonregel blijft een `receipt_table_line` of `purchase_import_line`.
- De keuze **Mijn artikel** schrijft uitsluitend de verwijzing `matched_household_article_id` naar `household_articles.id`.
- De artikelgroep is een eigenschap/relatie van datzelfde huishoudartikel via `household_articles.article_group_id`.
- Standaardverwerking is een eigenschap van datzelfde huishoudartikel via `household_articles.default_inventory_handling`.
- Een voorraadpositie is een projectie in `inventory` met `inventory.household_article_id` naar hetzelfde huishoudartikel, aangevuld met locatie en hoeveelheid.
- Een aankoop- of voorraadgebeurtenis verwijst naar hetzelfde `household_article_id`.

## Verboden dubbele bronnen

De volgende waarden mogen niet als zelfstandige functionele artikelidentiteit worden gebruikt:

- zichtbare artikelnaam;
- bontekst;
- `inventory.id`;
- een frontendoptie-ID of `live::`-alias;
- een gekopieerde artikelgroep op een importregel als permanente bron;
- een afzonderlijk "Mijn artikel"-record;
- een afzonderlijk "Voorraadartikel"-record.

Namen zijn presentatie. Alleen `household_article_id` bepaalt welk huishoudartikel bedoeld is.

## Gedrag per scherm

### Uitpakken

- Toont een gebruikersvriendelijke kolomnaam, maar kiest een `household_article_id`.
- Leest artikelgroep en standaardverwerking van `household_articles`.
- Mag een tijdelijke verwerking of locatie per importregel opslaan, maar maakt geen kopie van het huishoudartikel.

### Artikelgroepen

- Wijzigt `article_group_id` en standaardverwerking op `household_articles`.
- De wijziging is onmiddellijk zichtbaar in Uitpakken en Voorraad omdat alle schermen hetzelfde record lezen.

### Voorraad

- Toont voorraadposities gegroepeerd of uitgesplitst naar locatie.
- Iedere zichtbare actieve voorraadregel moet een geldige `household_article_id` hebben.
- Artikelnaam en artikelgroep worden via `household_articles` gelezen; zij worden niet als concurrerende waarheid uit `inventory.naam` afgeleid.

## Verwerkingscontract

1. Een importregel wordt gekoppeld aan exact één `household_article_id`.
2. De effectieve verwerking wordt bepaald uit een tijdelijke regelafwijking en anders uit `household_articles.default_inventory_handling`.
3. De financiële aankoopregistratie gebruikt altijd datzelfde `household_article_id`.
4. Bij normale opslag wordt `inventory` bijgewerkt met datzelfde `household_article_id`.
5. Bij directe consumptie wordt geen voorraadpositie gemaakt; aankoop en consumptie blijven wel aan hetzelfde huishoudartikel gekoppeld.

## Migratie- en opruimregel

Bestaande actieve voorraadregels zonder geldig `household_article_id`, met een verkeerd huishouden of met een tijdelijke alias moeten via een expliciete migratie worden hersteld of geblokkeerd. Nieuwe naamgebaseerde fallback- of synchronisatiecode is niet toegestaan.

## Structurele preventie van nieuwe huishoudartikelvervuiling

- Bij een **bewezen** Catalogus-/GTIN-identiteit wordt binnen het actieve huishouden het reeds gekoppelde `household_article_id` hergebruikt. Een afwijkende zichtbare naam maakt geen tweede huishoudartikel aan.
- Een kassabonomschrijving is geen bewezen centrale productidentiteit. Een retailergebonden bonartikelnummer is **geen** GTIN, en een niet-gescopeerde winkel-SKU mag niet als universele barcode worden gebruikt. Automatische winkelcodeherkenning vraagt een bestaande, expliciet bevestigde combinatie van **winkelketen + genormaliseerde kassabonomschrijving + bonartikelnummer**. Ook hetzelfde bonartikelnummer bij een ándere omschrijving mag niet automatisch een bestaande Cataloguskoppeling erven. Ontbreekt dit bewijs, dan blijft de bron ongekoppeld; een gebruiker kan de bestaande expliciete artikelkeuze of -aanmaak gebruiken.
- Een verwijzing naar een inmiddels verwijderd `household_article_id` of tijdelijke `live::`-alias mag nooit stilzwijgend via een naam opnieuw worden aangemaakt. Een bronregel mag de oude verwijzing verliezen, of uitsluitend een aantoonbaar bestaand canoniek huishoudartikel uit hetzelfde huishouden terugvinden.
- Automatische toekenning van een `global_product_id` aan een huishoudartikel dat aantoonbaar een andere productidentiteit of barcode heeft, wordt niet geforceerd. Een bronconflict wordt afgewezen zonder bestaande artikel-, bon- of voorraadgegevens te herschrijven.
- PostgreSQL-aankooptransacties serialiseren het koppelen/aanmaken van één specifieke combinatie `household_id + global_product_id`. Een blind database-unique-constraint over bestaande vervuilde historische records is niet toegestaan zonder aparte, objectief gevalideerde migratie.
- Deze preventie verwijdert of herstelt **geen** bestaande historische bonnen of huishoudartikelen. Het beschermt de write-path; eerdere inconsistente koppelingen vereisen afzonderlijk databeheer.

## Verplichte regressies

- Uitpakken kiest Appel en slaat het echte `household_article_id` van Appel op.
- Wijziging van artikelgroep bij Appel is zonder synchronisatiestap zichtbaar in Uitpakken en Voorraad.
- Normale aankoop verhoogt voorraad van hetzelfde huishoudartikel.
- Directe aankoop registreert het bedrag maar maakt geen voorraadpositie.
- Twee huishoudartikelen met dezelfde naam in verschillende huishoudens blijven volledig geïsoleerd.
- Herladen en F5 veranderen de gekozen artikelidentiteit niet.


## Platformbrede codevrije bonnaamherkenning is geen huishoudidentiteit

De beperking op automatische **winkelcodeherkenning** en de onafhankelijke
identiteit van `household_articles.id` blijven volledig van kracht.
Een uitzonderlijke **platformbrede** bronidentificatie kan na een expliciete
bevoegde actie een bonregel zonder winkelartikelnummer aan een reeds bestaand
centraal Catalogusproduct verbinden, uitsluitend wanneer minimaal één andere
bevestigde, genummerde bonregel met **exact dezelfde genormaliseerde bonnaam**
die ene Catalogusproduct-ID onafhankelijk bewijst en er nergens
tegenstrijdig identiteitsbewijs voor die naam bestaat. De naam geldt slechts
als stabiele alias van de bewezen centrale identiteit en maakt geen nieuwe
mondiale GTIN of synoniem tussen aparte Catalogusproducten. Deze actie voert
nooit zelfstandig een huishoudkoppeling, voorraadafboeking, bonmutatie of
historisch herstel uit; daarvoor blijven de eigen harde sleutel- en
bewijsvereisten gelden.


### Uitzondering op automatische identificatie van centrale bonnamen (14 november 2026)

De PO heeft uitdrukkelijk bepaald dat **exact gelijke bonnamen** met
**verschillende winkelartikelnummers** aan hetzelfde bestaande
Catalogusproduct mogen worden gekoppeld, binnen één winkel en over
verschillende winkels heen. Dit is alleen toegestaan via de bevoegde
centrale bonnaamroute en alleen als het oorspronkelijke product onafhankelijk
is bewezen en alle bestaande centrale claims eenduidig blijven.

Een door een bevoegde gebruiker bevestigde naamalias, bijvoorbeeld
HV Melk → Halfvolle melk, wordt platformbreed éénmaal vastgelegd en
geldt voor alle bonartikelen met die exacte aliasnaam. De alias
verandert geen oorspronkelijke bronbon, GTIN, Catalogusproduct,
product-product-synoniem, historisch huishoudartikel of voorraad.
Bestaande andere productclaims of bewaarde barcodes blokkeren
automatische verwerking. De harde regel dat het functionele
household_article_id de huishoudidentiteit is, blijft zonder uitzondering
bestaan.
