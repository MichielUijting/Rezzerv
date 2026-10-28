# Taxonomie-eerst proef 5: Shopify + CBS ECOICOPv2 + OFF

**Status:** uitsluitend read-only bewijsproef, geen productieimplementatie.

## Doel

Toets of InHuis de 43 Catalogus- en 1.161 ED2-artikelen uit de vorige proef
met bestaande, licentievrije gestandaardiseerde *aggregatieniveaus* kan beschrijven,
ook zonder barcode. Kwaliteit en onbekendheid zijn belangrijker dan kunstmatig
hoge dekking. De uitkomsten mogen nooit automatisch een `Artikelgroep`,
`Producttype`, GS1 Brick, winkelartikelkoppeling of bon veranderen.

## Referenties en geen licentieafdrachten

- Shopify Standard Product Taxonomy v2026-08 NL, MIT: lokale kopie van **14.606**
  officiële categorieën met volledige hiërarchie, zonder Shopify-account.
- CBS ECOICOPv2 2026, CC BY 4.0 met naamsvermelding: **440** codes en namen,
  beschrijft huishoudelijke bestedingsdoelen. CBS is geen productdatabase.
- Open Food Facts: alleen een kleine optionele steekproef van maximaal zes
  bestaande, geldige Catalogus-GTINs via bestaande InHuis-read-only service,
  minstens zes seconden tussen aanvragen. OFF is ODbL: controleer voor elk
  later productiehergebruik de databanklicentie en eventuele share-alike.
- Geen GS1-netwerkabonnement, geen betaalde licenties, geen model/API-key.

Zie `tools/taxonomy_proof5_references/NOTICE.md` voor versie-, auteurs-,
licentie- en SHA256-herkomst. Alle brongegevens voor Shopify/CBS zijn vooraf
versiegepind en verkleind: de PO hoeft tijdens de proef niets te downloaden.

## Methode

1. Bestaande PostgreSQL-backend uitlezen via expliciete read-only transactie
   en `rollback`; ED2-projectie hergebruiken.
2. Letterlijke Nederlandse categorie-naamherkenning; geen toekenning uit
   willekeurige voorouderwoorden. Een verschil tussen winkelartikelnaam en
   categorie blijft een onbevestigd voorstel.
3. Homoniemen, meerdere Shopify-paden, bewerkingsvormen en samengestelde
   artikelen expliciet uitlichten. Geen 'zeker' op basis van één woord.
4. CBS ECOICOPv2 vergelijken op letterlijke labels en via een **lokale brede
   vergelijkingssleutel** met Shopify-families; dit is geen officiële crosswalk
   en telt niet als tweede onafhankelijk bewijs.
5. Maximaal zes OFF-barcode-read-aanroepen na het afsluiten van de DB-transactie.
6. Alle regels en subtotalen in een alleen-lokaal TXT-rapport; geen datamutaties.

## Voorlopige offline replay van reeds verstrekt proef-4 verslag

Dit is de **tekstuele replay**, nog niet de nieuwe levende PostgreSQL-proef.
Gegevens staan niet in deze repository en worden niet als GitHub-artifact gepusht.

| Bron | Totaal | Exacte naam | Overige woordmatch | Meerdere Shopify-typen | Bereiding/ingrediënt/homoniem/nonfood waarschuwing | Geen match |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Catalogus | 43 | 4 | 0 | 0 | 1 | 38 |
| Bonartikelen ED2 | 1.161 | 87 | 135 | 15 | 12 | 912 |

**Nauwkeurigheid onbekend.** Ook 'exacte naam' is geen bewezen productidentiteit.
Bijvoorbeeld `TRIANGEL` lijkt in Shopify een muziekinstrument, maar kan in
een supermarkt een broodje zijn; `Tomaten gezeefd` is geen verse tomaat en
`SNOEP TOMAAT` is geen snoepgoed. Deze gevallen krijgen waarschuwingen.

## Randvoorwaarden voor vervolgstap

1. PO laat het losse 1-klikscript draaien; controleer aantal rijen, status en
   OFF-steekproef. Bij afwijkingen onderzoek, geen wijzigingen.
2. Handmatige blinde kwaliteitssteekproef over categorieën met minstens 30
   herkenningen plus twijfelgevallen, **niet** op basis van volume goedkeuren.
3. Definieer samen met PO welke gestandaardiseerde **brede** categorieën in
   huishoudcontext de gewenste `Productgroepen` en `Producttypes` vervangen.
4. Alleen na aparte besluitvorming een veilige gescheiden migratie ontwerpen
   met export, back-up, controle van samengestelde artikelen en rollback.
5. GS1-externe aansluitingen blijven apart en alleen na expliciet door een
   bevoegde gebruiker toegekende barcode, zoals door PO verlangd.

TEST_LEVEL_PROVISIONAL: L

Reden: nieuwe diagnostische tool met backend-/DB-connectie, onbekende
CI-padmapping, fail-closed L tot de normale releasecontrole dit bepaalt.

STYLEGUIDE_IMPACT: none

STYLEGUIDE_REASON: geen UI-wijzigingen.
