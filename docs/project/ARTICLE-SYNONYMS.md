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
Een winkelaanduiding komt uit de bevestigde centrale winkelkoppeling of een
expliciet herkende winkel als Catalogusbron. Alleen producten met één eenduidige
winkel worden voorgesteld; de twee winkels moeten verschillend zijn. Een
ontbrekende of dubbelzinnige winkel leidt niet tot een gefingeerde winkelnaam
of een te bevestigen paar. Productfoto's komen uitsluitend uit de opgeslagen
Catalogus-`image_url`, met de bestaande placeholder als er geen foto is.

De kandidaatselectie gebruikt de beproefde TF-IDF/cosine-baseline: woord-1/2-grams
en teken-3/5-grams, beide 50%, over Nederlandse naam en variant. Winkelwoorden
worden genegeerd. Er is geen Zalando-model/API en geen externe netwerkopvraag.
Een sparse index vermijdt een dense N×N-matrix. Kandidaten hebben minimaal 0,20
tekstovereenkomst en staan bij ten minste één artikel in de beste zeven. Dit is
uitsluitend een suggestiegrens, geen betrouwbaarheidsclaim. Er wordt op de hele
centrale set gezocht, niet uitsluitend op AH/Jumbo. Dezelfde GTIN of dezelfde
winkelcode is een exacte identiteit en geen synoniempaar. Bekende verschillende
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
Jumbo-product heeft waarde 1; zonder geldige directe koppelingen waarde 0.
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
