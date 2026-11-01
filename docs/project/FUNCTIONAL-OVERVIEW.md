# Functionele hoofdprocessen

## Kassabon naar voorraad

De beoogde keten is: kassabon ontvangen, OCR en parsing, regels controleren in Kassa, koppelen aan producten of huishoudartikelen en daarna verwerken naar Voorraad. **Uitpakken is alleen een tussenstap wanneer locatie-toewijzing daadwerkelijk actief is.** Als Uitpakken/Waar Inhuis niet actief is, gaat een goedgekeurde gewone voorraadregel rechtstreeks naar Voorraad met een echte locatievrije opslag (`space_id=NULL`, `sublocation_id=NULL`); de systeemterm **Direct** is daarbij geen voorraadlocatie en wordt niet als locatie geprojecteerd. Een artikel met afhandeling `DIRECT_CONSUMPTION` blijft daarvan strikt gescheiden: aankoop/consumptie wordt geregistreerd, maar er ontstaat geen voorraadmutatie. De som van de artikelen is leidend; het bon-totaal is een controlewaarde.

### Automatisch verbruik bij herhaalaankopen

Wanneer automatische afboeking voor een huishoudartikel actief is, worden meerdere aankopen van hetzelfde canonieke `household_article_id` op dezelfde kassabondatum als één cumulatieve productdag behandeld. De productdag is strikt huishoudgebonden en gebruikt de datum van de kassabon, niet de verwerkingsdatum. Daardoor kan voorraad die eerder op dezelfde dag is gekocht niet bij een tweede of later verwerkte kassabon opnieuw als oude voorraad worden afgeboekt. Een later verwerkte, maar eerder gedateerde kassabon op dezelfde kalenderdag blijft onderdeel van dezelfde productdag. Als geen bruikbare kassabondatum beschikbaar is, blijft de bestaande per-aankoopsemantiek gelden.

## Voorraad en artikelgroepen

Voorraad, locaties en artikelgroepen zijn huishoudgebonden. Artikelgroep moet zichtbaar en volgens rol wijzigbaar zijn. Beheeracties mogen alleen aan bevoegde gebruikers worden aangeboden.

## Productcatalogus en externe databases

**Externe databases 2** is een afzonderlijke platformactie naast Externe databases,
met dezelfde toegangsvoorwaarden. Overzicht en zoeken zijn alleen-lezen;
expliciet bevestigde koppeling en ontkoppeling zijn afzonderlijke bevoegde
schrijfacties. De standaardtabel toont alle bonartikelen uit de volledige
aankoopimport- en kassabonregelset, ook de gekoppelde en de wachtende.
Een bonartikel zonder officiële GS1-classificatie is uitdrukkelijk geen
voor Kassa/Voorraad bevestigde Cataloguskoppeling. Exact dezelfde getoonde
artikeltekst, winkelketen en bonartikelcode worden eenmaal getoond. Hoofdletters,
accenten en spaties binnen de naam blijven onderscheidend. Dit is uitsluitend
presentatiegroepering, geen wijziging
van productidentiteit of Cataloguskoppelingen. Zoeken, sorteren, kolombreedtes en paginering gebruiken de gedeelde
DataTable. Het laden van de artikellijst start geen externe zoekacties en
schrijft geen gegevens. Productkandidaten worden pas na artikelselectie gezocht.
Alleen actieve, voorraadgerechtigde productregels van niet-verwijderde bonnen
worden getoond, met de genormaliseerde artikelnaam en het winkelartikelnummer.
Statiegeld/emballage, kortingen, koop-/spaarzegels, betalingen en totalen zijn
geen artikelen voor deze lijst. Financiële regels blijven wel op de bon en
meetellen volgens de financiële bonregels. Uitpakken-importkopieën van een
kassabon worden niet opnieuw als zelfstandige bron gelezen: de actuele
regelrol en verwijderstatus van de oorspronkelijke bon blijven leidend.
Externe databases 2 toont geen knop Afsluiten.
Op desktop opent dubbelklikken op een artikel een productkandidatenpaneel onder de
tabel; op mobiel volstaat één tik. Enter of spatie ondersteunt toetsenbordgebruik.
De alleen-lezen productzoekroute gebruikt voor Lidl eerst het opgeslagen winkelartikelnummer
om een Nederlandse Lidl-productpagina te raadplegen. Alleen een uniek Product met
hetzelfde paginanummer én passende naam/variant wordt gebruikt. Een barcode moet
expliciet in dat Product of de bijbehorende Nuxt-productnode staan en een geldige
GTIN-controle hebben. Artikel-/ERP-/IAN-nummers worden nooit tot GTIN omgevormd.
Eén aangetroffen barcode wordt exact in OFF opgezocht; ontbrekende OFF-informatie
mag de Lidl-bron niet als zoekbewijs laten verdwijnen. Bij meerdere barcodes wordt niet willekeurig gekozen.
Zonder bruikbare Lidl-barcode wordt de bestaande automatische OFF-zoeklogica van Externe databases hergebruikt:
de server bepaalt artikelnaam/winkel uit de bron-ID, maakt dezelfde zoekvarianten
en suggesties, bewaakt product-/huismerkconflicten en rangschikt kandidaten.
Het paneel toont productkandidaten met naam, merk, barcode, inhoud, bron,
herkenning en overeenkomst, met standaard
zoeken, sorteren en paginering. De eerste volgorde blijft de bestaande automatische
voorkeursvolgorde. Een naamsuggestie blijft herkenbaar als suggestie. Een door Lidl vermelde barcode
blijft bronbewijs en is geen automatisch bevestigde Cataloguskoppeling.
Voor Albert Heijn en Jumbo wordt eveneens de winkelcatalogus geraadpleegd.
AH zoekt met de boncode/naam en vergelijkt uitsluitend het expliciete `hqId` met
de boncode. De aparte `webshopId` bepaalt de detailopvraag, waarvan het geretourneerde
product-ID gelijk moet zijn. Jumbo zoekt openbare productlinks en verifieert de
exacte SKU; bij een 401/403 op de product-API wordt de openbare productpagina met
dezelfde SKU gebruikt. Zonder boncodeovereenkomst blijft een winkelproduct een
zichtbare naamsuggestie. Naam-, variant-, huismerk- en GTIN-conflicten worden
geweerd; meerdere verschillende GTINs bij dezelfde boncode blijven ambigu.
Een unieke boncode/barcode-overeenkomst krijgt een exacte OFF-lookup; overige
winkelresultaten worden met de bestaande OFF-suggesties samengevoegd, ontdubbeld
op GTIN en begrensd tot twintig kandidaten. Een voorloopnul bij een geldige
GTIN-14 wordt voor de OFF-opvraag als equivalente GTIN-13 behandeld; dit is geen
conversie van een winkelartikelnummer. Een bronfout wist reeds gevonden geldige
winkelresultaten niet. Beide routes zijn anoniem, zonder klantaccount/cookies,
met vaste eigen winkelhosts, geen redirects, maximaal twintig verzoeken,
maximaal acht productdetails, acht seconden per verzoek, dertig seconden
netwerkbudget en 2 MiB per antwoord. Alleen een anonieme AH-gasttokenopvraag en
vaste read-only productqueries mogen POST gebruiken; geen login/winkelmand/order.
De onderste kandidatentabel toont op desktop en mobiel maximaal **7 kandidaten
per pagina**, met de bestaande paginering onder de tabel zodra er meer zijn.
Zoeken/sorteren geldt voor alle opgehaalde kandidaten en brengt pagina 1 terug.
De bovenste artikellijst behoudt haar bestaande paginering van 10 per pagina.
De onderste tabel laat een gebruiker op desktop door dubbelklikken, op mobiel
door één tik en via Enter/spatie een kandidaat ter bevestiging kiezen.
Dit is geen automatische koppeling: vóór het bevestigingsvenster haalt
Inhuis via de bestaande handmatige exacte OFF/GTIN-zoekroute een aan de
oorspronkelijke bonregel gebonden selectieproof op. Een kandidaat zonder
OFF-bewijs, bij een identiteitconflict of zonder geldige barcode wordt niet
gekoppeld; uitsluitend winkelbewijs blijft een onopgeslagen suggestie.
Het venster toont het bronartikel, het geverifieerde OFF-product en barcode.
Annuleren schrijft niets; alleen OK roept de bestaande bevoegde
`off/link-selected`-route aan. Na serverbevestiging ververst het overzicht
de actuele centrale Cataloguscode, classificatiestatus en tellers.
Een timeout wordt nooit als succesvolle koppeling gepresenteerd.

**PO-besluit 28 oktober 2026 — volledig ED2-overzicht:** Externe databases 2
toont alle unieke bonartikelen, ook wanneer ze al een centrale Cataloguskoppeling
hebben of wachten op een officiële GS1-classificatie. De aparte, bestaande
`unlinked-articles`-API behoudt zijn beperkte contract voor andere afnemers;
ED2 gebruikt het alleen-lezen `articles-overview`. De status wordt niet
afgeleid uit huishoudartikelen, bonartikelcodes of losse OFF-kandidaten.
De drie elkaar uitsluitende tellers **Niet gekoppeld**,
**Classificatie ontbreekt** en **Gekoppeld** tellen de volledige, op
winkelketen + exacte bontekst + bonartikelnummer ontdubbelde lijst en zijn
tegelijk statusfilters. De filterbare kolom **Art.code** toont uitsluitend
een gevalideerde GTIN van een centraal bevestigd of aantoonbaar opgeslagen,
nog te classificeren Catalogusproduct. Een bonartikelnummer wordt niet als
Catalogus-Art.code overgenomen. Generieke koppelingen blijven zonder GTIN
maar tellen wél als **Gekoppeld**. **Art.code** heeft een normaal tekstfilter
voor volledige of gedeeltelijke barcodes; **GS1-class.** (voorheen **Status**)
heeft een gewoon tekstfilter op de Nederlandse statusomschrijving. De
drie gekleurde statusknoppen werken onafhankelijk van beide tekstfilters;
een volledige statusnaam wordt exact gematcht (dus *Gekoppeld* niet ook
*Niet gekoppeld*).
**PO-besluit 28 oktober 2026 — GS1 aanvullen in ED2:** bij een expliciete
OFF-koppeling in status **Classificatie ontbreekt** opent de artikelselectie
het paneel **GS1-classificatie aanvullen**. Hier worden mogelijke officiële
Nederlandse GS1 GPC Brick-codes getoond en kan de gebruiker op code of
omschrijving in de officiële catalogus zoeken. Een suggestie is nooit een
automatische toewijzing: de gebruiker selecteert de Brick en bevestigt
**Classificatie opslaan** met **OK**; **Annuleren** schrijft niets. De server
controleert de oorspronkelijke bon-/OFF-identiteit en de wachtstatus opnieuw,
en schrijft de officiële GS1-productgroep plus de centrale GS1-toewijzing
in één transactie. Alleen als het bonartikel daarna aantoonbaar **Gekoppeld**
is volgt succes en verversen de tellers. De actie verandert geen bonnen,
huishoudartikelen of voorraad; ongeldige codes, conflicten en verouderde
koppelingen stoppen zonder gedeeltelijke opslag. Alleen gebruikers met de
reeds bestaande platformbevoegdheid voor externe productkoppelingen mogen
deze schrijfhandeling uitvoeren.
**PO-besluit 28 oktober 2026 — bulkacties ED2:** de volledige tabel heeft
een selectorkolom met een lege, smalle kolomkop. **Alles op pagina** selecteert
uitsluitend de zichtbare pagina en bewaart selectie van andere pagina's.
De acties staan onder de tabel: **Exporteren** levert uitsluitend de
geselecteerde artikelen met Artikel, Winkelketen, Bonartikelnummer, Art.code,
GS1-class. en Omvang / gewicht als semikolon-CSV (veilig tegen spreadsheetformules).
**Ontkoppelen** vereist minimaal één en maximaal honderd geselecteerde regels,
allemaal voorzien van een expliciete centrale OFF-koppelidentiteit. Een
bevestigingsdialoog met **Annuleren** en **OK** is verplicht. De backend
herleidt de bronidentiteiten opnieuw en vergelijkt elke actuele OFF-koppeling
met de selectie. Wordt één koppeling door andere bronartikelen gedeeld,
dan moeten ook die artikelen expliciet zijn geselecteerd. Een ongeldige,
onvolledige of verouderde bulkkeuze stopt als geheel zonder gedeeltelijke
ontkoppeling. Alleen de geselecteerde centrale OFF-relaties worden inactief;
Catalogusproducten, bronbonnen, aankoopregels, huishoudartikelen en voorraad
blijven intact. Een bewuste ontkoppeling onderdrukt tevens een eventuele oude
impliciete GTIN-herkoppeling; een nieuwe, expliciet bevestigde koppeling blijft
mogelijk. De tellers en tabel worden na de actie opnieuw geladen. Bij timeout
wordt geen succes geclaimd. Niet-OFF-koppelingen en uitsluitend via GTIN
afgeleide koppelingen zijn niet via deze bulkactie te verwijderen.
Het kandidaatpaneel toont na de vaste regel over beschikbare productgegevens
geen afzonderlijke uitleg, bronstatusalinea's of extra bronbewijsteksten. Een
knop **Zelf zoeken in OFF** opent een eigen scherm voor het geselecteerde
bonartikel. Daar kan de gebruiker met één vrij tekstinvoerveld productnaam,
merk en andere trefwoorden invullen. Zoeken start pas bij **Zoeken** of Enter;
de resultaten komen uitsluitend uit OFF en tonen maximaal **7 kandidaten per
pagina**, met paginering voor de overige resultaten (maximaal twintig per
zoekopdracht). De resultatentabel heeft geen tweede reeks filterinvoervelden.
In **Zelf zoeken in OFF** gebruikt de gebruiker één invoerveld voor een
omschrijving, merk of barcode. Invoer die uitsluitend uit cijfers bestaat,
wordt als barcode herkend: uitsluitend 8, 12, 13 of 14 cijfers zijn toegestaan.
Overige invoer wordt als tekst gezocht, ook als de omschrijving cijfers bevat.
Barcodezoeken gebruikt de exacte OFF-opvraag, controleert server-side het
GTIN-controlecijfer en gebruikt dezelfde servergegenereerde, kortlevende
koppelingproof en identiteits-/huismerkcontroles. Zoeken wijzigt geen Catalogus- of
voorraadgegevens; een onbekende barcode geeft een leeg resultaat en een
bronstoring een afzonderlijke foutmelding.
Het afzonderlijke OFF-scherm toont geen extra Terugknop. De geselecteerde
bonartikelnaam staat boven het zoekveld **vetgedrukt**. De zoekactie blijft
uitsluitend lezen; de Overeenkomstkolom is de relevante OFF-productnaam-score
zonder de winkelnaam als schijnbaar productbewijs en bepaalt de eerste rangorde.
Resultaten met uitsluitend winkelnamen en 0% overeenkomst worden weggefilterd.
Een dubbelklik (mobiel: tik, toetsenbord: Enter) op een kandidaat toont
uitsluitend **Weet u zeker dat u dit artikel wilt koppelen?** met knoppen
**Annuleren** en **OK**; geen titel of extra uitleg in die bevestiging.
Alleen bij OK controleert de server het bronartikel, de geldige GTIN,
het maximaal tien minuten geldige cryptografisch ondertekende zoekbewijs,
eventuele merkconflicten en of er een officiële GS1 GPC-classificatie bestaat. Dit bewijs
komt van het al door de backend gelezen OFF-zoekresultaat en is aan het
bronartikel en de GTIN gebonden; het is geen door de browser vertrouwde
productwaarde. Voor deze bevestiging volgt géén tweede externe OFF-aanvraag.
Een verlopen, onjuist of door een backendherstart vervallen bewijs wordt
afgewezen; dan moet opnieuw worden gezocht. Na **OK** keert de interface
na de serverrespons altijd terug naar **Externe databases 2**, ook als de
koppeling is afgewezen. Alleen een door de server bevestigde koppeling wordt
als geslaagd gemeld; het gekoppelde bronartikel blijft na herladen in het
volledige ED2-overzicht met zijn werkelijke status en eventuele Art.code.
Bij een afwijzing blijft het bronartikel
beschikbaar en blijft de reden als aanklikbare foutregel zichtbaar totdat de
gebruiker die sluit of naar een ander scherm gaat. Een mislukte schrijfactie
wordt nooit verward met een opgeslagen Catalogusartikel.
Bij een verzoek-timeout toont InHuis **niet bevestigd**: een afgebroken
clientverzoek bewijst niet dat de server geen koppeling heeft gemaakt.
**Annuleren** sluit alleen de dialoog en blijft op Zelf zoeken in OFF.
Daarna slaat de centrale Catalogusdienst het gevalideerde product platformbreed
op; deze mutatie maakt geen voorraad- of huishoudartikel aan. Een al compleet
Catalogusartikel mag op dezelfde GTIN worden hergebruikt. Voor een volledige
Kassa-/Voorraadkoppeling is een officiële GS1 GPC-classificatie verplicht.
Naast een expliciete geldige
GS1-code mag alleen een exact in de producttaxonomie vastgelegd en met de
actuele officiële Nederlandse GS1-referentie geverifieerd producttype worden
gebruikt; voor **Achterham** is dit de officiële code **10005781**
(voorbereid/verwerkt varkensvlees). Een onbekend, onjuist of dubbelzinnig
product wordt niet automatisch geclassificeerd: het product wordt met een
GTIN en `classification_pending` opgeslagen, maar nog niet voor Kassa/Voorraad
bevestigd.
Na opslag van een bestaand Catalogusartikel wordt bovendien gecontroleerd
of de bevestigde centrale koppeling daadwerkelijk naar precies dat artikel
verwijst; anders rolt de database de transactie terug.
De lijst zonder barcode en de centrale koppeling gebruiken dezelfde
winkelketensleutel (`store_chain` vóór `store_name`) en dezelfde
oorspronkelijke bonartikeltekst. Alleen een bevestigd geclassificeerd artikel of
een aantoonbaar opgeslagen GTIN-identiteit met `classification_pending` mag
daardoor verdwijnen uit de oudere lijst zonder barcode, maar niet uit het
volledige ED2-overzicht. Een ontbrekende officiële
GS1-classificatie geeft de melding *Classificatie ontbreekt*, zonder de
Catalogusopslag te blokkeren. Annuleren wijzigt niets. Na
**OK** keert de gebruiker na afloop terug naar Externe databases 2 met
een waarheidsgetrouwe succes- of foutstatus; op mobiel blijft de gedeelde
header-Terug beschikbaar.

De productpagina wordt anoniem gelezen, uitsluitend via HTTPS op www.lidl.nl,
met gecontroleerde redirects naar hetzelfde product, maximaal drie verzoeken,
een netwerkbudget van twaalf seconden en maximaal 2 MiB per antwoord. Er is
geen accountlogin, Scan&Go, buitenlandse koppeltabel of assortimentimport.
Zoeken start alleen na selectie en maakt geen Catalogus-, kandidaat-, huishoud-
of voorraadmutatie. Bij wisselen van artikel worden oude resultaten gewist en
lopende clientverzoeken afgebroken; een late respons mag het nieuwe paneel niet
overschrijven. Leeg resultaat, onbereikbare OFF-bron en rechtenfouten worden apart
afgehandeld; bij een zoekfout kan de gebruiker opnieuw zoeken.
Oude statiegeldregels die ten onrechte als product zijn opgeslagen, worden via
een afzonderlijk herstelplan hergeclassificeerd naar financieel/niet-voorraadgerechtigd.
De oorspronkelijke regel, bedragen, koppelingen en voorraadhistorie blijven behouden;
het openen van de lijst voert dit herstel niet uit.
Losse gewichtsdetails worden bij de Lidl-bronnormalisatie vóór Kassa/Uitpakken
samengevoegd indien de brongegevens dit bewijzen; bij twijfel vragen ze controle
en zijn ze niet voorraadgerechtigd. Bestaande bewezen dubbele bronregels kunnen
expliciet worden hersteld volgens [het herstelprotocol](WEIGHT-DETAIL-REPAIR.md).

Rezzerv scheidt centrale productkennis van huishoudartikelen en voorraad. Externe bronnen kunnen productgegevens verrijken. **Catalogus en Externe databases zijn platformbreed en gelden voor alle huishoudens.** Centrale catalogusmutaties zijn platformbeheeracties. Een huishoudspecifieke koppeling op een `household_article` is geen globale Cataloguskoppeling en mag een platformbrede externe-databasekoppeling niet blokkeren of als globale status worden geprojecteerd.

Voor bonartikelen bestaan twee geldige centrale koppelvormen:

- **Exact product:** wanneer een specifieke productidentiteit betrouwbaar bekend is, wordt gekoppeld aan een Catalogusproduct met geldige GTIN/EAN, bijpassende GTIN-identiteit en officiële GS1 GPC Brick. Een expliciete huismerkidentiteit in de bontekst (bijvoorbeeld `AH` bij Albert Heijn) blijft daarbij fail-closed: een extern exact product met conflicterend merk mag niet worden bevestigd.
- **Generiek artikel:** wanneer de kassabon het soort artikel wel betrouwbaar bepaalt maar merk, variant of GTIN niet, mag de gebruiker bewust informatieverlies accepteren en koppelen aan een generiek centraal Catalogusartikel. Dit artikel heeft een generieke naam en een officiële GS1 GPC Brick als classificatie-authority, maar **geen verplichte GTIN/EAN, merk of variant**. Voorbeeld: `AH BOUILLON` kan centraal worden gekoppeld aan `Bouillon` met de gekozen officiële Brick, zonder te doen alsof bekend is of het kip-, rund- of een andere exacte bouillonvariant was.

**PO-besluit 27 oktober 2026 — Catalogusopslag vóór GPC:** na expliciete
gebruikersbevestiging mag een betrouwbaar via OFF geïdentificeerd exact product
met een geldige GTIN én overeenkomende GTIN-identiteit reeds in de centrale
Catalogus worden opgeslagen, ook als een officiële GS1 GPC Brick ontbreekt.
De bronbonidentiteit en product/merkcompatibiliteit blijven verplicht. De
bijbehorende winkelartikelrelatie krijgt dan `classification_pending`; de UI
toont *Classificatie ontbreekt*. Dit is **niet** één van de twee volledige
koppelvormen: Kassa, Uitpakken en Voorraad mogen deze relatie niet als bevestigd
gebruiken zolang er geen officiële GPC Brick is. Het bronartikel verdwijnt wel
uit de oudere lijst zonder barcode, maar blijft in het volledige ED2-overzicht
staan als *Classificatie ontbreekt* met de gevalideerde Catalogus-Art.code.
Wanneer later een geldige officiële classificatie is vastgelegd, wordt de
bestaande wachtende relatie zonder bon-/huishoud-/voorraadmutatie als volledige
koppeling uitleesbaar. Zonder classificatie wordt nooit een Brick geraden.
De historische SQLite-migratiebaseline blijft onveranderd; deze nieuwe
wachtstatus hoort bij de reguliere PostgreSQL-database van Inhuis.

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

Externe databases bepaalt automatisch een centraal consumptie-/producttype uit
de officiële GPC Brick, beschikbare gestructureerde kenmerken en herkenbare
productomschrijvingen. De code en beslisgrenzen staan in
[AUTOMATIC-PRODUCT-TYPES.md](AUTOMATIC-PRODUCT-TYPES.md). Dit is een afgeleide
indeling; GTIN, centraal product, huishoudartikel en handmatige Artikelgroep
blijven afzonderlijke identiteiten.

Een compleet, niet-tegenstrijdig type telt voor Bijna op samen over winkels en
merken. Verpakkingsinhoud wordt afzonderlijk omgerekend. Er zijn geen verplichte
variantvelden of classificatiebevestigingen voor huishoudens. Onvoldoende
informatie geeft een automatische pending-status: het artikel blijft apart en
vraagt geen invoer. Herkenning wordt opnieuw beoordeeld wanneer centrale
productgegevens veranderen. Een onzekere match wordt nooit als feit opgeslagen.

De eerste expliciete regelset dekt zestien productfamilies. Dit is geen claim
van volledige assortimentsdekking of een nieuwe officiële GS1-typecode. De
bestaande veilige exacte/generieke productkoppeling blijft de autoriteit voor
het koppelen van een bonartikel; automatische categorisering keurt geen
onzekere bon- of productidentiteit goed.

## Winkels en importinstellingen

Winkelkoppelingen en importinstellingen bepalen hoe aankopen en kassabonnen binnenkomen. Beheer hiervan is huishoudgebonden en voorbehouden aan de juiste beheerrol.

## Meldingen

Er bestaat op 22 juli 2026 nog geen actieve meldingen-API. Een toekomstig meldingsdomein moet eerst opnieuw worden geïnventariseerd en beveiligd.

## Artikel-synoniemen

Superusers en alle actieve Frontteamleden kunnen via de actie **Artikel-synoniemen**
centrale artikelen met een code/barcode vergelijken. De standaardtabel toont
voorgestelde paren uit verschillende aantoonbare winkels met zeven kolommen:
selectie en per artikel naam, Catalogusfoto en winkelnaam. De centrale
DataTable biedt zoeken, sorteren, kolombreedtes en paginering. Selectie plus
**Koppelen** bevestigt alle geselecteerde paren als bulk en is zonder selectie
inactief. Een aparte knop Vernieuwen ontbreekt. De bevestigde relatie staat in
de centrale Catalogus (`article_synonym_links`).
In het Catalogusoverzicht, de mobiele lijst en het artikeldetail staat
**Gekoppelde winkels**: het aantal unieke **andere** winkels dat rechtstreeks
via bevestigde synoniemparen aan het artikel is gekoppeld (zonder transitieve
afleiding). Nul betekent dat geen geldige directe winkelkoppeling kan worden
geteld. De selectorkolom in Artikel-synoniemen heeft geen zichtbare titel en is
smal, met behoud van de toegankelijke checkboxnamen.
Er is geen automatische bevestiging. Bestaande product-, verpakking- en
huishoudidentiteiten blijven behouden. Ontbrekende codes worden eerst aangevuld
via Externe databases 2. Zie [het functionele contract](ARTICLE-SYNONYMS.md).

### PO-besluit 31 oktober 2026 — tabelcontext en handmatige barcode

Wanneer de gebruiker vanuit het Catalogusoverzicht of Externe databases 2
naar detail en terug navigeert, blijven pagina, filtering en sortering behouden
op desktop en mobiel, ook na Zelf zoeken in OFF. Alleen wanneer een pagina
door een veranderde resultaatset niet meer bestaat wordt de paginapositie
veilig begrensd.

Externe databases 2 biedt naast handmatig OFF zoeken een expliciete
bevestigingsactie voor het invoeren van een geldige GTIN/EAN. Eerst zoekt
de server de barcode exact in Open Food Facts. Een verifieerbaar, met het
bonartikel verenigbaar OFF-resultaat wordt via de bestaande gecontroleerde
Cataloguskoppeling opgeslagen; beschikbare productgegevens en afbeelding
worden overgenomen en ontbrekende officiële GS1-classificatie blijft
onbevestigd. Is de barcode niet in OFF bekend, dan wordt uitsluitend de
gebruikersbevestigde barcode als afzonderlijk, platformbreed winkelartikelbewijs
bewaard. De kolom **Ingevoerde barcode** toont dit apart; **Art.code**,
**Gekoppeld** en de Kassa-/Voorraadprojectie worden er niet stilzwijgend door
aangepast. Conflicten, ongeldige controlesommen of onbereikbaarheid van OFF
leiden niet tot een verzonnen bevestiging.

#### Verduidelijking barcode opslaan bij OFF-storing (31 oktober 2026)

De hoofdtafelkolom **Art./Barcode** toont de vastgelegde artikelcode, of bij
ontbreken daarvan de handmatig ingevoerde barcode (met aanduiding dat deze nog
niet als Cataloguskoppeling is geverifieerd). Een afzonderlijke barcodekolom is
niet nodig. Wanneer OFF tijdelijk niet bereikbaar is, slaat Inhuis na expliciete
gebruikersbevestiging uitsluitend de geldige barcode op. De melding maakt
onderscheid tussen een werkelijk niet bij OFF gevonden code en een niet
uitgevoerde OFF-controle wegens storing. Bij herstel van OFF kan dezelfde
barcode opnieuw worden aangeboden voor gecontroleerde productverrijking.


#### Herstel persistent zichtbare barcode in Externe databases 2 (31 oktober 2026)

De platformbrede overzichtroute projecteert handmatig opgeslagen barcodebewijs
zelf op de bestaande winkelartikelidentiteit. Winkelcodes zoals `Albert Heijn`,
`albert-heijn` en `ah` worden aan de serverkant op dezelfde canonieke
presentatiecode herleid; bontekst en winkelartikelnummer blijven deel van
de exacte koppelsleutel. Hierdoor blijft de barcode ook na een nieuwe
schermopbouw of browserherstart onder **Art./Barcode** zichtbaar zonder
dat een niet-bevestigde barcode als Catalogus- of GS1-koppeling telt.


#### OFF-identiteit: compacte schrijfwijze AlbertHeijn en centrale melding

Wanneer een bonartikel expliciet een AH-huismerk aangeeft, beschouwt Inhuis
het OFF-merk **AlbertHeijn** (zonder spatie) als dezelfde identiteit als
**Albert Heijn** of **AH**. Kandidaten van andere merken blijven voor een
exacte koppeling geblokkeerd door dezelfde backendcontrole; handmatige
bevestiging omzeilt die controle niet. Als een kandidaat niet kan worden
gekoppeld, toont het scherm de concrete reden in de centrale overlay
**Melding** via `AppFeedbackProvider` en niet als inline foutregel.
