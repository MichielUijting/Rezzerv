# Catalogusidentiteit per kassabonartikel — PO-besluit 12 november 2026

Status: functioneel PO-contract voor de Catalogus en de koppeling van bonartikelen.

## Begrippen

- **Kassabonomschrijving**: de tekst van het artikel op de kassabon, voor de identiteit stabiel genormaliseerd (spaties, hoofdletters en leestekens).
- **Bonartikelnummer**: de originele winkelartikelcode op die kassabon; voorloopnullen blijven behouden.
- **Artikel-/barcode**: de GTIN/EAN van één actief Catalogusproduct; geen bonartikelnummer.
- **Winkelketen**: canonieke retailer, waarbij bewezen aliassen zoals AH / Albert Heijn of Lidl / Lidl Nederland hetzelfde domein vormen.

## Uniciteit

**(Winkelketen, kassabonomschrijving, bonartikelnummer) → maximaal één Artikel-/barcode.**

Een kassabonomschrijving kan bij dezelfde winkelketen meerdere bonartikelnummers hebben. Die nummers kunnen bewust naar hetzelfde Catalogusproduct verwijzen. Het bonartikelnummer *alleen* mag dus niet bepalen dat twee verschillende kassabonomschrijvingen hetzelfde artikel zijn.

Wanneer de drie bronvelden aanwezig zijn, moet de herkenning de volledige combinatie gebruiken. Als een oude bron de omschrijving mist, is een code-only koppeling alleen bruikbaar als die eenduidig is. Bij meerdere mogelijke producten of conflicterende bewijsbronnen is de uitkomst *conflict*, niet een willekeurige match.

Voorbeeld:

| Winkel | Bontekst | Bonartikelnummer | Artikel-/barcode |
|---|---|---|---|
| Lidl | Melk halfvol | 0012345 | 8712345678906 |
| Lidl | Melk halfvol | 0087654 | 8712345678906 |
| Lidl | Yoghurt naturel | 0012345 | andere unieke GTIN |

De eerste twee regels zijn toegestaan. De laatste regel is alleen toegestaan als de volledige bonomschrijving+code naar één ander product verwijst; code-only herkenning moet bij twijfel stoppen.

## Beheer en gegevensbehoud

- Een platformbevoegde beheerder kan in Catalogusdetail de huidige combinaties bekijken, de juiste koppeling expliciet bevestigen, een bronbewezen bonartikelnummer toevoegen en een exact afgebakende foutieve koppeling corrigeren.
- Een nieuwe combinatie mag alleen worden toegevoegd als die aantoonbaar op een bestaande, niet-verwijderde fysieke productbonregel voorkomt en de doelbarcode uniek hoort bij een actief Catalogusproduct.
- Een correctie mag geen bestaande household-article-, voorraad-, bon-, event- of classificatiegegevens wijzigen. Als reeds bestaande huishoudartikelen aan de oude productidentiteit hangen, moet de correctie afzonderlijk beoordeeld worden.
- Geen automatische samenvoeging van huishoudartikelen; `household_articles.id` blijft de huishoudspecifieke identiteit.
- Een bevestiging of correctie wordt toegeschreven aan de werkelijke ingelogde bevoegde gebruiker.
- Bij historische incomplete of conflicterende identiteiten: toon een controleerbare fout, schrijf niets en laat de bron ongewijzigd.

## Verplichte regressies

1. Gelijke bontekst, verschillende bonartikelnummers mogen beide worden bevestigd.
2. Gelijke bonartikelcode, verschillende bontekst kunnen bij een verschillend Catalogusproduct horen.
3. Gelijke volledige broncombinatie naar twee verschillende Catalogusproducten is een conflict.
4. Een bron zonder bevestigde omschrijving mag niet stilzwijgend door een tekstmatch worden gekoppeld.
5. Een onjuiste of ontbrekende kassabonbron blokkeert het handmatig toevoegen.
6. Correctie met bestaande huishoudartikelverwijzingen of concurrente wijzigingen stopt zonder voorraad-/bonmutatie.
7. Bevestigen vereist platformpermissie en legt de werkelijke beoordelende gebruiker vast.


## Historische conflicten beoordelen in Catalogus

De functie **Catalogus → Historische conflicten beoordelen** berekent de actuele conflictlijst voor uitsluitend het via de serversessie geautoriseerde huishouden. Zij gebruikt hetzelfde historische backfill-previewcontract en de exacte keten `purchase_import_lines → receipt_table_lines → household_articles`, nooit een koppeling op naamgelijkheid. **Herzien PO-besluit 12 november 2026:** elke reguliere Beheerder (canonieke huishoudrol `owner` of `admin`), waaronder een Frontteamlid met huishoudbeheerrechten, mag alleen de conflicten van het **eigen actieve reguliere huishouden** lezen en boncodecombinaties bevestigen. Een Superuser kan uitsluitend Systeemhuishouden 0 beoordelen en behoudt daarvoor de bestaande platformpermissie `platform.external_products.link_existing`. Een regulier Beheerder krijgt géén algemene platform-Cataloguspermissie. Gewone Gebruikers en onbevoegde platformrollen krijgen geen toegang.

- **GET /api/catalog/household-identity-conflicts** is alleen-lezen en toont per conflicterend huishoudartikel de daadwerkelijke boncombinaties, herkenningsstatus en eventuele Cataloguskandidaten. Bij een afgekapt brononderzoek worden geen te beoordelen regels vrijgegeven.
- **POST /api/catalog/household-identity-conflicts/confirm-source** hercontroleert onder één transactie de exacte bronregel binnen het geautoriseerde huishouden, de fysieke productregel, de ongewijzigde winkel/omschrijving/boncode, de checksum en unieke actieve eigenaar van de gekozen GTIN, eventuele originele bonbarcode, tegenstrijdige bestaande huishoudkoppeling en legacy-code-only-koppelingen. Daarna wordt uitsluitend de centrale winkelcodecombinatie bevestigd via de bestaande expliciete bevestigingsservice.
- De server accepteert in deze routes geen vrij te kiezen `household_id`. De ingelogde actor is bepalend voor de audit-attributie. Onjuiste bron, dubbele identiteit, gewijzigde feiten of onzekere historische koppeling geeft een fout zonder gedeeltelijke wijziging.
- De 21 eerder waargenomen conflicten zijn geen hardcoded programmalijst. Het scherm toont de actuele, uit brondata afgeleide conflictgroepen. Na bevestiging van een boncode kan een huishoudartikelconflict blijven bestaan, omdat geen enkel `household_article_id`, `inventory`, `receipt` of bestaande koppeling wordt herverdeeld.
- Bestaande meervoudige huishoudartikelen met hetzelfde Catalogusproduct vereisen een afzonderlijk, expliciet te beoordelen behoud-/samenvoegbesluit. Bevestiging van een bonbarcode is **niet** toestemming voor een huishoudartikelmerge.

### Zichtbaarheid in het Systeemhuishouden

De functie blijft household-scoped en wordt nooit automatisch op een ander huishouden gericht. Een Superuser met `context_type=system` en huishouden `0` ziet de actie **Historische conflicten beoordelen** en kan uitsluitend de bonregels van **Systeemhuishouden 0** beoordelen. Een reguliere Beheerder, ook wanneer die geen Frontteamrol heeft, kan uitsluitend het eigen actieve huishouden beoordelen. Een Frontteamlid met Beheerderrechten volgt dezelfde huishoudscope.

**Er is geen toegang tot kassabon- of huishoudartikelgegevens van andere reguliere huishoudens.** De 21 eerder geïdentificeerde conflicten uit `huishouden1` zijn dus niet zichtbaar in een Superuser-/Systeemhuishouden-0-sessie, maar wél te beoordelen door een **regulier Beheerderaccount van huishouden1**. Er is daarvoor geen Frontteamrol, accountwissel binnen Superuser of supporttoegang vereist. De API accepteert geen browser-aangeleverd huishouden; de backend controleert de canonieke sessie, actuele huishoudrol, actoridentiteit en household-isolatie voor lezen én bevestigen. Desktop en mobiel voeren dezelfde zichtbaarheidstoets uit, met negatieve backend- en Playwrighttests.


### Toegang via regulier Beheerderaccount

Een Superuser ziet bij een leeg Systeemhuishouden-overzicht een duidelijke instructie: log in met een **regulier account dat Beheerder is van het huishouden met de conflicten**. Daar is in Catalogus direct dezelfde historische beoordeling beschikbaar. De eerdere Frontteam-toewijzingsomweg is vervallen; Inhuis kent voor dit doel geen rollen toe en toont geen huishoudenselectie waarmee de systeemcontext kan worden omzeild.

Bevestigen is een strikt bronbewezen actie voor de centrale winkelketen + kassabonomschrijving + bonartikelnummer naar één Catalogus-GTIN. Daarmee kan centrale herkenning ook voor andere huishoudens bruikbaar worden; er worden echter geen bonnen, voorraadregels, huishoudartikel-ID's of bestaande huishoudkoppelingen van andere huishoudens aangepast. Bij een afwijkende bestaande Catalogusidentiteit, legacy-koppeling of onzekere bron volgt een weigering zonder gedeeltelijke wijziging. De Beheerder krijgt hierbij uitsluitend deze afgebakende beoordelingsfunctie, niet het algemene beheer van centrale Catalogusproducten.

De historische lijst blijft volledig datagedreven. De eerdere read-only telling van 21 conflicten uit huishouden1 is geen gegarandeerde actuele telling; dit moet in de echte lokale Beheerderssessie worden geverifieerd. Een bevestigde bonartikelcombinatie corrigeert geen voorraad en voegt geen huishoudartikelen samen.


### Beoordeling van meerdere conflicten in het standaard tabelcomponent

De handmatige beoordeling heeft twee stappen en gebruikt op desktop en mobiel uitsluitend de canonieke `DataTable` met selectievakjes, kolomfiltering, sortering, kolomresize en paginering (10 per pagina). Alle bewerkingsknoppen staan **onder** de tabellen in de bestaande actiesectie; er zijn geen per-regel-acties. De gebruiker selecteert één of meer conflicterende huishoudartikelen en opent met **Bonregels beoordelen** de oorspronkelijke bonregels van die selectie. Het scherm toont daar ook de *andere huishoudartikelen uit hetzelfde geautoriseerde huishouden* die op dezelfde Cataloguskandidaat uitkomen. Dit betreft leesbewijs, geen voorstel tot samenvoeging.

De geselecteerde bonregel(s) kunnen daarna via de actie **Barcode bepalen** onder de tweede tabel worden beoordeeld. Meerdere bronregels mogen als één centrale boncodecombinatie worden bevestigd **uitsluitend wanneer winkelketen, genormaliseerde kassabonomschrijving en bonartikelnummer exact overeenkomen**; één bewezen bronregel is dan voldoende voor die ene centrale sleutel. Verschillende combinaties worden niet automatisch als hetzelfde product geïnterpreteerd en moeten afzonderlijk worden beoordeeld. De bestaande API valideert de fysieke bron, het actieve huishouden, de barcode en bestaande centrale identiteit; tegenstrijdigheden blijven fail-closed. Er vindt géén batchmutatie van huishoudartikelen, voorraad of historische bonnen plaats.

De beoordeling wordt geopend als een aparte browsergeschiedenis-entry via `/catalogus?historischeConflicten=1`. Het openen van de bonregels voegt de expliciet geselecteerde huishoudartikel-ID's toe aan de URL, maar **geen** household-ID; de backend bepaalt en valideert de household-scope. De native browserterugknop keert terug naar de conflictlijst en vervolgens naar Catalogus. De schermen hebben geen eigen terug- of sluitknop.

Een reden als **Meerdere huishoudartikelen bij één Catalogusproduct** bewijst *niet* dat de winkelcode of barcode onjuist is. Het kan gaan om meerdere huishoudartikel-ID's die historisch naar dezelfde Cataloguskandidaat verwijzen. Een correcte boncode bevestigen haalt zo'n conflict niet noodzakelijk uit de lijst. Een echte consolidatie van huishoudartikel-ID's met hun voorraadhistorie vraagt een afzonderlijk expliciet PO-besluit en een apart gecontroleerd migratie-/mergecontract; deze PR automatiseert dat niet.
