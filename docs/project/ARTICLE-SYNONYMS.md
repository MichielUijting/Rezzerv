# Artikel-synoniemen

PO-opdracht 26 oktober 2026. TEST_LEVEL_PROVISIONAL: L.

De nieuwe actie **Artikel-synoniemen** en route `/artikelsynoniemen` zijn beschikbaar
voor Superusers **of** actieve Frontteamleden. Beide mogen dezelfde suggesties
bevestigen. Reguliere huishoudrollen, Platformbeheerder-only en IP-owner-only
geven geen toegang. De API controleert de actuele serversessie en canonieke
`platform.external_products.view` / `platform.external_products.link_existing`
permissions, plus de speciale functionele rol. Er worden geen extra algemene
Catalogusbeheerrechten aan Frontteam toegekend.

De bron is uitsluitend centrale Cataloguskennis, nooit privéhuishoudartikelen.
Een actief centraal artikel komt in aanmerking met een geldige barcode of een
bevestigde centrale winkelartikelcode. Een winkelcode is altijd voorzien van de
winkelnaam; een winkelcode wordt nooit omgezet in een barcode. Artikelen zonder
code/barcode moeten eerst in Externe databases 2 worden aangevuld. Deze wijziging
voegt aan dat bestaande scherm geen nieuwe opslagroute toe.
De winkelherkomst is uitsluitend een informatief bronveld en **geen eis voor een
synoniemvoorstel of een handmatige bevestiging**. Een onbekende winkel, twee
gelijke winkels of twee verschillende winkels beïnvloeden de overeenkomstscore
niet en blokkeren de koppeling niet. De winkel mag nooit uit de artikelnaam
worden verzonnen. Productfoto's komen uit de opgeslagen Catalogus-`image_url`.

De kandidaatselectie gebruikt de beproefde TF-IDF/cosine-baseline: woord-1/2-grams
en teken-3/5-grams, beide 50%, over Nederlandse naam en variant. Winkelwoorden
worden genegeerd. Er is geen Zalando-model/API en geen externe netwerkopvraag.
Een sparse index vermijdt een dense N×N-matrix. Kandidaten hebben minimaal 0,20
tekstovereenkomst en staan bij ten minste één artikel in de beste zeven. Dit is
uitsluitend een suggestiegrens, geen betrouwbaarheidsclaim. Er wordt op de hele
centrale set gezocht, niet uitsluitend op AH/Jumbo. Dezelfde GTIN of dezelfde
centrale winkelartikel-identiteit is een exacte identiteit en geen afzonderlijk
synoniempaar; twee onafhankelijke artikelen van dezelfde winkel mogen uiteraard
wel een synoniemvoorstel zijn. Bekende verschillende
GPC Bricks worden uitgesloten; ontbrekende kenmerken worden niet verzonnen.

De standaard DataTable bevat exact zeven kolommen: **lege selectiekop**, **Artikelnaam**,
**Foto artikel**, **Winkel**, en nogmaals **Artikelnaam**, **Foto artikel**,
**Winkel** voor de tweede winkel. Elke rij is precies één voorstel voor een
relatie tussen twee verschillende centrale Catalogusartikelen. Zoeken, sorteren,
kolombreedtes en de bestaande centrale pagineringscomponent volgen de DataTable
(10 per pagina, navigatie wanneer er meer resultaten zijn). Selectie blijft over
pagina's/filters bestaan. **Koppelen** is
de expliciete handmatige bevestiging voor maximaal 200 gekozen paren tegelijk.
De knop is inactief bij nul geselecteerde rijen. Alleen aanvinken of het scherm
openen schrijft niets. Er is geen knop **Vernieuwen**.

De backend valideert ieder paar opnieuw tegen actuele suggesties en een
fingerprint van de getoonde productfeiten. Bij een verouderd/ongeldig paar wordt
de gehele bulk afgewezen met 409; bestaande selectie blijft zichtbaar zodat
vernieuwen bewust gebeurt. Herhaling met ongewijzigde feiten is idempotent.
Productrijen worden in vaste volgorde vergrendeld. De unieke gesorteerde
paaridentiteit voorkomt dubbele of omgekeerde relaties. Opgeslagen zijn actor,
tijd, methode, score en fingerprint. Een bevestiging verdwijnt uit de suggesties
en blijft na herladen bewaard in de centrale Catalogus-relatietabel
`article_synonym_links`.

Dit is een directe relatie tussen twee centrale producten. Er wordt geen
transitieve gelijkheid afgeleid: A↔B en B↔C bewijzen niet A↔C. GTINs, producten,
verpakkingen, household_article_id, Artikelgroepen, bonnen en voorraad blijven
zelfstandig bestaan. Deze eerste functie geeft Bijna op of boodschappen geen
nieuwe automatische aggregatie; de bestaande automatische consumptietypes
blijven daarvoor leidend. Een hoge tekstscore is geen bewijs voor dezelfde smaak,
bereiding of samenstelling; de gebruiker vergelijkt de zichtbare productgegevens.

De **Catalogus** toont per product de numerieke kolom **Gekoppelde winkels**;
dezelfde waarde staat in de mobiele Catalogus en beide detailpresentaties. Dit
is het aantal **unieke andere winkels** waaraan het product **rechtstreeks** via
een bevestigde synoniemrelatie is gekoppeld: een AH-product gekoppeld aan één
Jumbo-product heeft waarde 1; zonder bekende andere winkel waarde 0.
Deze teller is alleen een herkomstweergave en zegt niets over de geldigheid
van de synoniemrelatie.
Meerdere gekoppelde producten uit dezelfde andere winkel tellen eenmaal.
Een keten A↔B en B↔C telt C niet automatisch voor A. Alleen winkels met één
eenduidige, actuele centrale winkelaanduiding tellen mee; ontbrekende,
tegenstrijdige of verwijderde winkelgegevens worden niet als winkel verzonnen.
De teller is afgeleid bij het lezen, wordt niet dubbel opgeslagen en is
filterbaar, sorteerbaar en beschikbaar in de Catalogus-export. Er worden geen
huishoudartikelen of kassabondata geraadpleegd voor deze telling.

Alembic maakt uitsluitend `article_synonym_links`, met foreign keys, unieke
paarvolgorde en onderhoudsschrijfbarrière. Downgrade verwijdert alleen deze
nieuwe relaties. Bestaande catalogus-/huishoudgegevens worden niet teruggevuld.
Catalogusverwijdering verwijdert gekoppelde relaties via FK cascade.

Validatie: `backend/tests/test_article_synonyms.py` dekt ranking, identiteiten,
codegrens, beide rollen, ontbrekende rechten, requestgrenzen, stale bulk,
idempotentie, actoropslag en geïsoleerde migratie/downgrade. De eigen gefocuste
CI draait deze tests. De toegevoegde Playwright-spec draait in het bestaande
frontend-regressiecommando en dekt 390/1280 px voor beide rollen, selectie over
pagina/filter, foutbehoud, expliciete bulk, reload en weigering regulier account.
De bestaande PostgreSQL-foundation-, onderhouds-, rollen-, identity- en F7-gates
blijven aanvullend vereist; synthetische tests vervangen die niet.


## Synoniemenanalyse — eerste leesfase (29 oktober 2026)

De Catalogus biedt voor Superusers en Frontteamleden het scherm **Synoniemenanalyse**.
Dit gebruikt uitsluitend bestaande centrale, gecodeerde actieve Catalogusproducten,
rechtstreeks bevestigde artikelparen en bestaande tekstkandidaten. Er worden geen
huishoudartikelen, bonnen, barcodegegevens, voorraad of relaties gewijzigd.

Het nieuwe, beveiligde read-only endpoint
`/api/external-databases/article-synonyms/analysis` toont:
- aantal rechtstreeks bevestigde winkeloverstijgende paren en open tekstkandidaten;
- aantallen zonder gevonden tekstkandidaat en met onbekend winkelbewijs;
- artikelgroepen per bevestigde Shopify-artikelclassificatie, anders GS1 Brick,
  anders expliciet **Niet geclassificeerd**;
- aantallen artikelen met bevestigde directe koppelingen en open kandidaten per
  artikelgroep en winkel, plus doorklik naar de bestaande handmatige bevestiging.

Een product kan tegelijk een bevestigde relatie en nog niet beoordeelde kandidaten
hebben. **Geen kandidaat** betekent uitsluitend dat het bestaande algoritme geen
kandidaat heeft gevonden; het bewijst niet dat de winkel geen equivalent verkoopt.
Een ontbrekende winkel wordt niet als echte supermarkt meegeteld.
De tekstscore is geen waarschijnlijkheidspercentage en geen bewijs van
functionele gelijkwaardigheid. Geen automatische toekenning, geen transitieve
koppelingen, geen afwijzingsregistratie en geen assortimentimport in deze fase.
Verbeterde kenmerkmatching en vastleggen van afwijzingen zijn afzonderlijke
vervolgstappen.


## PO-acceptatie Synoniemenanalyse: 0/1/2/3+ tellers en kandidaatkeuze

De vier tellers tellen **artikelen** (niet unieke winkels) met respectievelijk
0, 1, 2 of minstens 3 **rechtstreeks bevestigde andere Catalogusartikelen**.
Een bevestigd paar telt voor beide deelnemende artikelen; duplicaten en
transitieve relaties tellen niet dubbel. Alleen actieve, eenduidig aan
verschillende winkels gekoppelde gecodeerde producten tellen mee, conform
het centrale synoniemcontract. De vier aantallen omvatten precies de zichtbare
analysepopulatie; aangeklikte teller filtert de artikeltabel, tweede klik heft
het tellerfilter op. Overige zoek-/winkelfilters zijn onafhankelijk.

De hoofdtabel toont direct de individuele Catalogusartikelen en hun aantal
rechtstreeks bevestigde synoniemen. Na artikelkeuze wordt in het paneel eronder
maximaal vijf voorstellen getoond. De kandidaten zijn exact een subset van de
bestaande handmatig te bevestigen `suggest_pairs`-voorstellen; de server
levert dezelfde fingerprints en hercontroleert die binnen de bestaande
atomische `/link`-transactie. Bij ontbrekende winkelidentiteit komt geen
zelfbedacht winkeloverstijgend voorstel. Voorstellen zijn geen bewezen
functionele equivalenten en worden nooit automatisch bevestigd.

Een dubbelklik op één kandidaat schrijft via dezelfde bevoegde route als
het selectierondje + **Merk kandidaat aan als synoniem**. Een enkele selectie
schrijft niets. Succes ververst de server-afgeleide lijst en tellers;
beide Catalogusproducten tonen bij nieuwe lezing de directe koppeling.
Geen update aan barcode, productidentiteit, huishouden, voorraad of kassabon.


### PO-verfijning: hoofdregel opent pas op dubbelklik

Het kandidaatpaneel wordt pas door een **dubbelklik op de hele hoofdartikelrij**
geopend. Een enkele klik verandert de selectie niet en toont geen kandidaatpaneel.
Artikelnaam en foto staan in de bestaande DataTable zonder aparte artikelknop.
Ook via Enter op een gefocuste rij is het paneel toegankelijk. Er zijn geen
wijzigingen aan de dubbele bevestigingsroute binnen de kandidaat-tabel of aan
opslag, autorisatie en Catalogusprojectie. Overbodige losse toelichtingen rondom
de tabellen zijn uit het werkscherm verwijderd.


### Compacte filters en scrollbar — PO, 29 oktober 2026

De vier tellers blijven het enige aanvullende filter boven de standaardtabel.
De losse artikelsoort-, winkel- en artikelzoekvelden boven de hoofdtabel
vervallen: de bestaande filtervelden in de DataTable zijn leidend.
De bestaande DataTable blijft tien rijen per pagina tonen. Op dit specifieke
Synoniemenanalyse-scherm wordt de gedeelde maximale scrollhoogte lokaal
losgelaten, zodat de horizontale scrollbar aan de onderkant van de **hele**
tabel staat en geen tabelrij of tekst bedekt. Dezelfde lokale regel geldt
voor de kandidaat-DataTable (maximaal vijf regels). De knop **Sluiten**
naast de kandidaat-tabeltitel vervalt; dubbelklik op een andere hoofdregel
laadt de kandidaten voor dat artikel. Bestaande selectie-, dubbelklik- en
bevestigingsfunctionaliteit blijft gehandhaafd.


## Doorwerking van bevestigde winkelherkomst (3 november 2026)

Artikel-synoniemen normaliseert aantoonbare winkelherkomst uit bevestigde centrale
`external_article_product_links` en expliciete Catalogusbron: onder meer
Albert Heijn/AH en Lidl/Lidl Nederland GmbH verwijzen naar dezelfde winkelketen.
Een Catalogusproduct met meerdere **bevestigde** winkelrelaties behoudt alle
winkels in de leesprojectie. Deze projectie is uitsluitend informatief:
een synoniemvoorstel en een handmatige bevestiging zijn altijd
**winkelonafhankelijk**. Handmatige bevestiging blijft vereist.

Dit is geen backfill uit ruwe kassabonnen. De winkel op een kassabon bewijst
uitsluitend de herkomst van de aankoop, niet de identiteit van het Catalogusproduct.
Een niet-bevestigde `matched_global_product_id`, naamsovereenkomst, GTIN-match
zonder bewaakte identiteit of huishoudartikelrelatie wordt **niet** tot
platformbrede winkelkoppeling verheven. Ontbrekende productidentiteiten moeten
eerst via de bestaande expliciete ED2-bevestigingsroute worden vastgelegd.
Dit voorkomt onderlinge vermenging van huishoudens en verandert geen bonnen,
Catalogusartikelen, voorraad, codes of synoniemrelaties.

## Artikel-synoniemen: zichtbaar artikeloverzicht bij nul voorstellen (3 november 2026)

De actie `/artikelsynoniemen` toont voortaan als hoofdtabel **alle actieve,
gecodeerde centrale Catalogusartikelen** uit de bestaande beveiligde
`/api/external-databases/article-synonyms/analysis`-leesprojectie, ook wanneer
`/api/external-databases/article-synonyms` geen nieuwe voorstellen bevat.
De tabel toont artikelnaam/foto, bewezen winkelherkomst (of expliciet
`Winkel onbekend`), aantal rechtstreeks bevestigde synoniemen, aantal
open voorstellen en status. Zoek-, sorteer- en paginering verlopen via de
bestaande DataTable. Dubbelklik of Enter op een artikel selecteert de context
en opent de bestaande zevenkoloms voorstel- en bulkbevestigingstabel;
zonder gekozen artikel blijven eventuele algemene voorstellen beschikbaar
voor de bestaande bulkroutine.

Deze UI-wijziging creëert geen nieuwe winkel/productidentiteit.
Een ontbrekende bevestigde winkelrelatie wordt zichtbaar gemaakt en niet
op basis van bontekst, naam of huishoudcontext aangevuld. Een volle lijst
Catalogusartikelen betekent niet dat er bevestigbare synoniemen zijn.
Na bevestigen worden beide tabellen opnieuw van de centrale backend geladen.

## Hergebruik oudere expliciet bevestigde winkel-productrelaties (3 november 2026)

Naast `external_article_product_links.status='confirmed'` hergebruikt de
alleen-lezen synoniemenprojectie nu ook bestaande centrale
`external_product_candidates` met `is_user_confirmed=TRUE`,
`status='linked_to_catalog'`, `candidate_status='linked_to_catalog'`,
een vastgelegde `global_product_id` en een niet-lege, bewezen winkelcode
uit de oorspronkelijke Kassa-/ED2-context. Historische bevestigingen die
nog niet in de nieuwere centrale koppeltabel zijn opgenomen verdwijnen
daardoor niet langer uit de winkelherkenning.

Alleen gekende winkelketens tellen mee. Tegenstrijdige product-ID's
binnen dezelfde (winkel, context_key) worden genegeerd. Voorstellen,
onbevestigde kandidaten, ontkoppelingen, verdwenen tabellen en vrije
tekst-/naamovereenkomsten vormen nooit shopbewijs. De projectie maakt
geen nieuwe globale identiteit en schrijft niets naar bonnen,
`external_article_product_links`, voorraad of huishoudgegevens.
Dit bewijst niet dat iedere kassabonregel een bevestigde
Catalogusidentiteit heeft; resterende ontbrekende links vereisen
gerichte bronketendiagnose en expliciete bevestiging.

## Correctie PO-besluit: winkel is geen criterium voor synoniemen (3 november 2026)

Het expliciete actuele PO-besluit vervangt alle eerdere passages in dit
document die verschillende bekende winkels als voorwaarde voor het voorstellen
of bevestigen van synoniemen beschreven. Productovereenkomst wordt gerangschikt
op naam en productkenmerken, onafhankelijk van winkel. Ook artikelen met een
onbekende of dezelfde winkel zijn handmatig koppelbaar. Een bevestiging is een
bewuste beslissing van de bevoegde gebruiker op twee **bestaande centrale
product-ID's**; het is geen automatische koppeling van een kassabon,
huishoudartikel, barcode of winkel. GTIN-identiteitsconflicten en verschillende
bekende GPC Bricks blijven uitgesloten. Het bestaande endpoint valideert
de kandidaat en fingerprint opnieuw voordat het opslaat.

Winkelherkomst mag wel afzonderlijk uit bestaande bewezen bon/productrelaties
worden geprojecteerd of gecorrigeerd, maar het ontbreken ervan blokkeert
Artikel-synoniemen nooit. De oudere `name_only`-presentatieblokkade is vervallen.
De `include_name_only`-argumentnaam wordt uitsluitend voor bestaande callers
tijdelijk behouden; alle suggesties volgen dezelfde winkelonafhankelijke logica.


## PO-correctie — twee afzonderlijke artikeltabellen, 4 november 2026

De pagina `/artikelsynoniemen` heeft twee onafhankelijke DataTables **naast
elkaar op desktop**, op smalle schermen onder elkaar. De **linkertabel** toont
de actieve gecodeerde centrale Catalogusartikelen; één klik of Enter selecteert
een canonieke product-ID (naam en artikel-/barcode onderscheiden lookalikes).
De **rechtertabel** bevat ieder ander actief gecodeerd centraal
Catalogusartikel exact één keer en toont drie volgordegroepen:

1. **Al gekoppeld** — rechtstreeks bestaande `article_synonym_links`, herkenbaar
   geaccentueerd; niet nogmaals selecteerbaar.
2. **Voorstel** — niet-bevestigde, door de bestaande naamscore voorgestelde
   kandidaten.
3. **Overig** — alle resterende gecodeerde Catalogusartikelen; de bevoegde
   gebruiker kan een bewust handmatig paar kiezen, ook zonder minimale tekstscore.

De gekozen linker-ID mag rechts nooit voorkomen. Zelfkoppelingen worden ook
server-side geweigerd. Twee identieke namen met **verschillende** centrale
product-ID's zijn niet automatisch hetzelfde record en krijgen hun
onderscheidende artikel-/barcode te zien. Een andere Catalogus-ID met een
identieke GTIN, overlappende bevestigde winkelartikel-identiteit of
strijdige bekende GPC Brick is **niet koppelbaar**, wordt als zodanig
gemarkeerd en krijgt nooit een nieuwe synoniemrelatie.

Een klik of Enter op een koppelbare rechterrij selecteert die voor een
nieuwe koppeling; **alleen expliciet Koppelen** schrijft via de bestaande
bevoegde `POST /link` route. Er kan tot 200 paren per batch worden gekozen.
De backend valideert live de twee bestaande product-ID's, de actuele
fingerprint en de identiteits-/GPC-beperkingen opnieuw, zonder op de
frontendnaam te vertrouwen. Voor een niet-automatisch voorgesteld paar stuurt
de client `manual=true`; de opslag vermeldt
`method='manual_catalog_review_v1'` en score 0. Een bestaand paar wordt
niet dubbel gemaakt. Geen automatische catalogusidentiteit-, winkel-,
voorraad-, bon- of huishoudwijzigingen.

Deze twee DataTables vervangen uitsluitend de oude zevenkoloms tabel die twee
kanten van één paar als afzonderlijke artikelen leek te tonen. Zoek-, sorteer-
en paginafunctionaliteit blijft centraal via DataTable. De metadata en
bestaande winkelherkomst zijn informatief; de winkel blijft volledig
onafhankelijk van de synoniemmatch.

De PostgreSQL-migratie bevat al de checkconstraint
`left_product_id < right_product_id`, die opslag van zelfkoppelingen op
de canonieke synoniemenrelatietabel verhindert. De nieuwe API-voorcontrole
voorkomt dat een ongeldig verzoek pas door de database wordt afgewezen.


## PO-verfijning 4 november 2026 — compacte uitgelijnde tabellen en ontkoppelen

De twee onafhankelijke DataTables beginnen op desktop op **precies dezelfde
hoogte**. Beide tabellen hebben uitsluitend vier kolommen:
**selectievakje, foto, artikelnaam, barcode**. Er is geen winkelkolom of
getoonde selectieteller. Links is maximaal één centraal Catalogusproduct
actief; de aangevinkte rij is de linkerkant van alle acties. Rechts mag de
gebruiker tot 200 individuele andere artikelen aanvinken.

Rechts geven achtergrondaccenten de **status ten opzichte van het gekozen
linkerartikel** aan: *lichtgroen = reeds rechtstreeks gekoppeld*,
*oranje = nieuw automatisch voorstel*, *geen arcering = overig*.
Arcering is **geen selectie**. Checkboxselectie is onafhankelijk daarvan.
Bij identieke namen onderscheiden barcode en de interne centrale ID de
verschillende artikelen.

De actie **Koppelen** is uitsluitend beschikbaar wanneer aangevinkte
artikelen rechts nog niet gekoppeld zijn en koppelbaar zijn.
**Ontkoppelen**, rechts naast Koppelen onderaan de rechtertabel, is
uitsluitend beschikbaar voor aangevinkte, reeds bestaande directe relaties.
De selectie telt geen dubbele paren en een artikel mag nooit aan zichzelf
worden gekoppeld. Na iedere bevestiging worden beide tabellen opnieuw uit
de serverbron gelezen en vervalt de selectie.

De nieuwe bevoegdheidsbewaakte `POST /unlink` gebruikt dezelfde
Superuser/Frontteam-grens als `POST /link`; voor **alle** aangevinkte paren
worden bestaande relatie, actuele product-ID's en fingerprint binnen één
PostgreSQL-transactie herbevestigd. Bij afwijking volgt een 409 en geen
gedeeltelijke ontkoppeling. Ontkoppelen verwijdert uitsluitend de gekozen
rijen uit `article_synonym_links`. Het herstelt of verwijdert **geen**
Catalogusartikel, GS1 GPC- of CBS-classificatie, kassabon, voorraad- of
huishoudgegevens. Historisch geërfde classificatie blijft behouden en
vereist afzonderlijk expliciet beheer als die onjuist zou zijn.


## Laatste functionele presentatieverfijning (4 november 2026)

De PO heeft de synoniemenfunctie functioneel akkoord bevonden met drie
laatste aanpassingen: beide standaardpagineringen op desktop op **gelijke
hoogte**, de twee bestaande knoppen **Koppelen** en **Ontkoppelen**
**onder** de rechterpaginering (niet erin), en per rij van de linker
Catalogustabel een **synoniemteller**. De teller gebruikt
`synonym_count` uit `build_synonym_analysis`, het aantal **direct**
bevestigde links, geen afgeleide transitieve groep. Beide tabellen houden
hun eigen filters, sortering, paginering en centrale tabelcomponent;
alleen links komt de extra tellerkolom. De bestaande directe
koppel-/ontkoppel- en classificatievoorwaarden veranderen niet.


## Laatste PO-aanpassing — compacte barcode en selectie met waarschuwing (4 november 2026)

Op de linker DataTable wordt de barcodekolom smaller gezet, samen met
compacte breedtes voor selectie/foto/naam, zodat de laatst getoonde teller
zichtbaar is zonder horizontaal scrollen op de gangbare desktopweergave.
De tellerkop heet **Syn.** en blijft het aantal direct bevestigde
synoniemrelaties van het Catalogusartikel tonen.

Alle rechterartikelen blijven met hun checkbox **selecteerbaar**, ook
wanneer de server reeds een identiteits- of GPC-conflict herkent. Daardoor
is het onderscheid tussen een gekozen artikel en een nog niet
koppelbaar artikel zichtbaar en toetsbaar; de selectie is **geen**
bevestiging. Wanneer één of meer geselecteerde nieuwe artikelen niet
koppelbaar zijn, weigert Koppelen de hele batch vóór verzending met
een verklarende foutmelding. De backend blijft de bestaande harde
GTIN-/winkelartikelcode- en GPC-conflictcontroles bij daadwerkelijk
koppelen handhaven. Er wordt geen uitzondering voor conflicterende
classificaties of artikelen ingevoerd, en geen deelbatch stilzwijgend
weggeschreven. Bestaande gekoppelde regels blijven via Ontkoppelen
beheersbaar. De tekst en link onder de tabellen naar
**Externe databases 2** vervallen op dit scherm.


## PO-verfijning linker tabelbreedtes (4 november 2026)

De linker tabel benut de beschikbare horizontale ruimte beter, zonder de
tabelcomponent of andere schermen te wijzigen. De checkbox- en fotokolom
hebben dezelfde standaardbreedte als rechts (42 en 70 px). De overblijvende
ruimte gaat naar Artikelnaam (236 px); Barcode blijft 112 px en de kolom
Syn. blijft 52 px. Zo krijgt de linker tabel dezelfde totale nominale
breedte als de rechter tabel en blijft de directe synoniemteller zichtbaar.
Paginering, filtervelden en handmatige kolomverstelling blijven via de
standaardcomponent werken.


## PO-verzoek 4 november 2026 — conflict uitleg in Inhuis-overlay

Een onveilige selectie via **Koppelen** toont geen in-screen-fouttekst
meer. De standaardcomponent **Melding** (`AppFeedbackProvider`) toont
een blijvende overlay met de twee betrokken artikelnamen, de concrete
oorzaak en het vervolg. De bestaande geselecteerde regels blijven
aangevinkt en **er wordt niets opgeslagen**.

De server levert per rechterartikel een gestructureerd conflicttype,
uitleg met echte bronwaarden en de toepasselijke herstelroute:
- `same_gtin`: beide verschillende Catalogusrecords dragen exact dezelfde
  barcode; de gedeelde GTIN staat vermeld en de overlay biedt
  **Naar Catalogusdetail** van het rechterartikel.
- `shared_article_code`: de records delen een bevestigde artikelcode;
  de code staat vermeld, met dezelfde detailroute.
- `gpc_mismatch`: beide bestaande officiële GS1 GPC Bricks verschillen;
  beide codes staan vermeld en de overlay biedt **Naar GS1 GPC**
  (`/catalogus/gpc-classificeren`) om indien toegestaan een **onjuiste**
  classificatie eerst te corrigeren.
- `same_article`/`missing_article`: geen actie die een ongeldige
  productidentiteit automatisch kan herstellen.

De overlay laat via **Sluiten** annuleren. Alleen voor daadwerkelijk
corrigeerbare brondata is er een navigatieactie naar bestaande
functionaliteit; zonder passende rechten blijft de bestaande autorisatie
gelden. Na een feitelijke correctie kan de gebruiker de synoniemkeuze
opnieuw controleren en handmatig met **Koppelen** bevestigen.
Er komt **geen** knop 'Toch koppelen' die officiële GTIN-identiteit of
bekende tegenstrijdige GS1 GPC-classificaties omzeilt. Een gedeelde GTIN
kan betekenen dat beide Catalogusrecords feitelijk hetzelfde artikel zijn,
niet twee synoniemen. Geen database-/migratie- of autorisatiewijzigingen.


**Beperking bestaande barcode-editor:** `CatalogBarcodeEntry` verschijnt
uitsluitend wanneer `primary_gtin` ontbreekt. De knop
`Bekijk Catalogusdetail` is bij een gedeelde bestaande barcode daarom
een **lees-/beoordelingsroute**, geen belofte dat de barcode daar direct
gewijzigd kan worden. Correctie van een bestaande foutieve GTIN vraagt
een afzonderlijke bevoegdheidsbewaakte identiteitsbeheerroute en maakt
uitdrukkelijk geen deel uit van deze PR.
