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

De functie **Catalogus → Historische conflicten beoordelen** berekent de actuele conflictlijst voor uitsluitend het via de serversessie geautoriseerde huishouden. Zij gebruikt hetzelfde historische backfill-previewcontract en de exacte keten `purchase_import_lines → receipt_table_lines → household_articles`, nooit een koppeling op naamgelijkheid. Alleen een Frontteamlid in de eigen reguliere huishoudcontext of een Superuser in de eigen Systeemhuishouden-0-context krijgt toegang, steeds met de bestaande platformpermissie `platform.external_products.link_existing`. Een gewone huishoudbeheerder of een andere platformrol heeft geen toegang, zelfs niet bij een losse technische platformpermissie.

- **GET /api/catalog/household-identity-conflicts** is alleen-lezen en toont per conflicterend huishoudartikel de daadwerkelijke boncombinaties, herkenningsstatus en eventuele Cataloguskandidaten. Bij een afgekapt brononderzoek worden geen te beoordelen regels vrijgegeven.
- **POST /api/catalog/household-identity-conflicts/confirm-source** hercontroleert onder één transactie de exacte bronregel binnen het geautoriseerde huishouden, de fysieke productregel, de ongewijzigde winkel/omschrijving/boncode, de checksum en unieke actieve eigenaar van de gekozen GTIN, eventuele originele bonbarcode, tegenstrijdige bestaande huishoudkoppeling en legacy-code-only-koppelingen. Daarna wordt uitsluitend de centrale winkelcodecombinatie bevestigd via de bestaande expliciete bevestigingsservice.
- De server accepteert in deze routes geen vrij te kiezen `household_id`. De ingelogde actor is bepalend voor de audit-attributie. Onjuiste bron, dubbele identiteit, gewijzigde feiten of onzekere historische koppeling geeft een fout zonder gedeeltelijke wijziging.
- De 21 eerder waargenomen conflicten zijn geen hardcoded programmalijst. Het scherm toont de actuele, uit brondata afgeleide conflictgroepen. Na bevestiging van een boncode kan een huishoudartikelconflict blijven bestaan, omdat geen enkel `household_article_id`, `inventory`, `receipt` of bestaande koppeling wordt herverdeeld.
- Bestaande meervoudige huishoudartikelen met hetzelfde Catalogusproduct vereisen een afzonderlijk, expliciet te beoordelen behoud-/samenvoegbesluit. Bevestiging van een bonbarcode is **niet** toestemming voor een huishoudartikelmerge.

### Zichtbaarheid in het Systeemhuishouden

De functie blijft household-scoped en wordt nooit automatisch op een ander huishouden gericht. Een Superuser met `context_type=system` en huishouden `0` ziet de actie **Historische conflicten beoordelen** en kan uitsluitend de bonregels van **Systeemhuishouden 0** beoordelen. Een Frontteamlid heeft een regulier huishouden, is daar Beheerder en kan uitsluitend dat eigen huishouden beoordelen.

**Er is geen toegang tot kassabon- of huishoudartikelgegevens van andere reguliere huishoudens.** De 21 eerder geïdentificeerde conflicten uit `huishouden1` zijn dus niet zichtbaar in een Superuser-/Systeemhuishouden-0-sessie. Dat vereist afzonderlijk geautoriseerde toegang tot die specifieke huishoudcontext en wordt niet geïntroduceerd in deze PR. De API accepteert geen browser-aangeleverd huishouden en controleert speciale rol, context, platformpermissie en household-isolatie. Desktop en mobiel voeren dezelfde zichtbaarheidstoets uit, met negatieve backend- en Playwrighttests.
