# Automatische producttypen in Externe databases

## Doel en acceptatie

Inhuis bepaalt zonder verplichte gebruikersinvoer welk winkel-/merkproduct voor
Bijna op equivalent is aan andere producten. Een concrete GTIN blijft een
concreet centraal product; het afgeleide consumptietype is een extra indeling.
Een huishoudartikel en de vrije huishoudelijke Artikelgroep veranderen niet.

- AH en Lidl halfvolle koemelk delen hetzelfde type bij dezelfde bewaring.
- Volle/magere melk, lactosevrij en andere melkbronnen blijven onderscheiden.
- Goudse jonge, jong belegen en oude kaas en verschillende vetklassen blijven
  onderscheiden. Geraspte kaas wordt onderscheiden van stuk/plak.
- Appelrassen en kooktypen van onbewerkte aardappelen blijven onderscheiden.
- Merken, winkelketens, GTIN en verpakkingsgewichten bepalen de typesleutel niet.
- Onvoldoende, onbekende of tegenstrijdige kenmerken geven `pending`, geen
  verplichte vraag aan de gebruiker en geen nieuwe aggregatiesleutel.
- Een bon met alleen `kaas` of `appels` levert geen verzonnen rijping of ras op.
- Kassa-/Uitpakkenstatus, bestaande bevestigingsgrenzen voor exacte/generieke
  productidentiteit en voorraadmutaties blijven afzonderlijk.

## Beslisvolgorde

1. Gebruik centrale productgegevens en beschikbare gestructureerde bronkenmerken.
2. Controleer de officiële Nederlandse GPC Brick en bijbehorende productfamilie.
3. Herken alleen gedeclareerde producttermen en kenmerkwaarden. Langere termen
   gaan bij overlap voor: `jong belegen` is niet ook `jong` en `belegen`.
4. Tegenstrijdige omschrijving/bronkenmerken of een onverenigbare Brick blokkeren
   het type. Een tweede bron wordt niet stil over een conflict heen gezet.
5. Een complete combinatie krijgt een stabiele interne sleutel met regelversie,
   Brick, productsoort, onderscheidende kenmerken en relevante bijzondere claims.
6. Verpakkingsinhoud blijft apart: ml/cl/dl naar l, gram/mg naar kg, expliciete
   multipacks naar totale inhoud. Aantallen en gewicht worden niet omgerekend
   zonder betrouwbare conversie. Meerdere onduidelijke hoeveelheden blijven leeg.

Voor melk legt de regelset de gebruikelijke productconventies expliciet vast:
zonder afwijkende melkbron of lactosevrijclaim wordt gewone koemelk/reguliere
melk bedoeld. Deze afleiding staat in de evidence als `productconventie`, niet
als door GS1 aangeleverd feit. Expliciete andere bronwaarden hebben voorrang;
plantaardige melk met een dierlijke melk-Brick blijft pending.

## Bronnen en grenzen

GS1 GPC is de categorie-authority; aanvullende GDSN/productgegevens kunnen
vetklasse, kaassoort, rijping en andere kenmerken leveren. Beschikbare
productomschrijvingen worden aanvullend met expliciete NL/EN-termen herkend.
Deze interne consumptietypes zijn geen nieuwe officiële GS1-codes.

De eerste regelset bevat **16 productfamilies en 24 kenmerkdefinities**: melk,
kaas, appels, aardappelen, brood, pasta, rijst, eieren, gehakt, noten, yoghurt,
chips, water, koffie, thee en wijn. De exacte ondersteunde waarden staan in
`backend/app/data/product_consumption_policy.json`. Deze dekking is bewust
begrensd: niet ieder ras, smaak, merknaam of wereldwijd assortiment is bekend.
Onbekende soorten en waarden blijven pending en worden niet op een grove Brick
samengevoegd. Nieuwe kennis wordt als centrale regeldata toegevoegd, zonder
nieuwe product-specifieke Pythonvoorwaarden of invoer door huishoudens.

De bestaande bronzoekketen blijft actief. Deze wijziging voegt geen nieuwe
betaalde databron, generatieve AI-afhankelijkheid of achtergrondcrawler toe.
Nieuwe metadata wordt bij de volgende bestaande bron-/Catalogusverwerking
opnieuw beoordeeld. Pending blijft bruikbaar in het bestaande bonproces; het
ontbreken van een consumptietype keurt een onzekere productidentiteit niet goed.

Referenties:

- https://ref.gs1.org/standards/gpc/
- https://ref.gs1.org/guidelines/gdm-implementation/
- https://ref.gs1.org/voc/cheeseMaturationPeriodDescription

## Opslag, compatibiliteit en terugwerkende werking

`global_product_consumption_profiles` bevat één afgeleid profiel per centraal
product, de beperkte bronfeiten, resultaat/evidence, regelversie en fingerprint.
Opslag gebeurt atomair met de bestaande centrale exact/generiek-koppeling.
Er worden geen sessies, volledige providerpayloads of huishoudgegevens bewaard.

Bestaande centrale producten zonder opgeslagen profiel worden read-only uit hun
actuele productgegevens beoordeeld. Opgeslagen kenmerken worden eveneens tegen
de actuele centrale naam, variant en Brick beoordeeld; een oude sleutel wordt
niet blind hergebruikt. Bestaande verwerkt geregistreerde aankopen kunnen daardoor
direct bijdragen, zonder bonnen opnieuw in te lezen of huishouddata te wijzigen.

De huishoudprojectie gebruikt voor complete types uitsluitend canonieke
huishoudartikel-ID's binnen het actieve huishouden. Een groep heeft één signaal
en een stabiele representatieve verpakking. Grenswaarden gebruiken de hoogste
omgerekende minimum-/streefvoorraad. De aankoopvoorspelling telt productdagen en
weegt fysieke hoeveelheden. Een onjuist onderliggend voorraad-/eventsaldo kan
niet door een saldo van een ander groepslid worden gemaskeerd.

Onvolledige producten behouden de bestaande afzonderlijke productroute. Het
nieuwe type vervangt geen voorraad-SSOT. Verbergen/overzetten onderdrukt het
hele complete groepssignaal; de bestaande herstelactie maakt het weer zichtbaar.

De migratie maakt uitsluitend de nieuwe centrale afgeleide tabel en index.
Downgrade verwijdert alleen deze reproduceerbare profielen. Er is geen
destructieve bon-, huishoud- of voorraadbackfill. Handmatige variantvelden uit
de eerdere Draft zijn verwijderd; eventuele eerder opgeslagen testinstellingen
worden niet gebruikt en niet gewist.

## GPC-suggesties

Bereidingswoorden en fuzzy spellingovereenkomst vormen zelfstandig geen
productbewijs. `Ongebrand` mag daardoor niet matchen op
`brand-/graveergereedschap`. Nederlandse labels van de meegeleverde officiële
publicatie worden aan de snapshot getoetst, zodat een afwijkend label geen
bewijs voor een andere officiële code kan vormen. Onduidelijke suggesties
worden niet automatisch bevestigd.

## Validatie

Gerichte tests dekken winkel-/merk-/taalonafhankelijkheid, verschillende
verpakkingen, onderscheidende kenmerken, ontbrekende/conflicterende informatie,
de amandelen-regressie, dataminimalisatie en de gedeclareerde dekkingsgrenzen.
De bestaande PostgreSQL/API-authority bewijst centrale profielopslag,
huishoudisolatie, groepsvoorspelling, verbergen/herstellen en ongewijzigde events.
Browserregressies controleren automatisch resultaat/pending zonder invoervelden
op 390 en 1280 pixels. De bestaande keten-, identity-, autorisatie-, migratie-
en F7-gates blijven vereist; gerichte tests vervangen die niet.
