# Taxonomie-eerst – proef 6: alleen gecodeerde centrale Catalogus

**Status:** read-only haalbaarheidsproef; geen productiemutatie en geen merge-/deployautorisatie.

## Besluit van Product Owner (28 oktober 2026)

De oorspronkelijke onderzoeksvraag is: kunnen we met **herbruikbare, gratis
gestandaardiseerde aggregatieniveaus** artikelen indelen als bijvoorbeeld
Groente, Zuivel of Frisdrank, met Shopify en CBS als taxonomieën, zonder
betaalde GS1- of andere licentieafdrachten?

**Vernauwde proef 6:** uitsluitend centrale `global_products` uit de
InHuis-Catalogus die *al* een waarde in `primary_gtin` hebben. Niet de
1.161 ongekoppelde bonartikelen uit ED2; niet de nog ongecodeerde artikelen.
De bestaande Catalogus kan naast barcodes ook een interne artikelcode
bevatten. Alleen een code met geldige GTIN-checkdigit van 8, 12, 13 of 14
cijfers is opvraagbaar bij OFF. De overige reeds gevulde codes worden
afzonderlijk gerapporteerd, nooit als barcode behandeld.

## Exacte bronnen en betaalvoorwaarden

- **Shopify Standard Product Taxonomy v2026-08:** 14.606 NL-categorieën met
  gestandaardiseerde hiërarchie en dezelfde 764 voedsel/dranken-ID's uit de
  officiële Engelstalige publicatie; MIT, bronbestand lokaal meegeleverd.
  Engelstalige labels dienen om OFF-tags te herkennen, Nederlandse paden zijn
  de output. Geen Shopify-account of betaalde Shopify-API nodig.
- **Open Food Facts:** bestaande read-only API voor **exact** bekende GTIN's
  om productnaam en OFF-categorieën op te halen; ten minste 6 seconden tussen
  GET-aanvragen, geen retries, maximaal 100 verschillende GTIN's. De database
  van OFF kent ODbL-verplichtingen bij later systematisch hergebruik. Deze proef
  voegt geen OFF-productdump aan de repo of aan de InHuis-database toe.
- **CBS ECOICOPv2 2026:** 440 officiële NL bestedingscodes, CC BY 4.0. Een
  *door InHuis gemaakte, indicatieve* crosswalk vanaf een Shopify-ID naar
  CBS is geen officiële CBS-productclassificatie.

Volledige herkomst en kopievoorwaarden in
`tools/taxonomy_proof5_references/NOTICE.md`.

## Verwerking en veiligheid

1. Lees bestaande Catalogusrijen `id, name, primary_gtin, status` in één
   PostgreSQL-`SET TRANSACTION READ ONLY`-transactie; expliciete `rollback`.
2. Verzamel alleen reeds gevulde GTIN's met geldige checkdigit. Dedupliceer
   dezelfde code, en roep pas **na** beëindiging van de transactie OFF aan.
3. Gebruik bestaande `lookup_off_product_by_gtin` uitsluitend voor
   opzoeken van die gevalideerde code. OFF moet exact dezelfde code
   teruggeven en `mutated: false` melden. Geen online zoekactie op naam.
4. Match OFF `en:`-categorietags tegen de **officiële Engelse Shopify-namen**
   en toon de corresponderende **Nederlandse** hiërarchie. Een handvol
   gedocumenteerde brede uitzonderingen (zoals `soft-drinks` naar Soda) blijft
   zichtbaar als *lokale vertaalsleutel*, niet als exact productbewijs.
5. Voorkom misleidende matches: gepureerde aardappel is niet zomaar een verse
   aardappel; meerdere Shopify-takken geven status **MEERDUIDIG**; verschil
   tussen productnamen en samengestelde gerechten geven waarschuwingen.
6. Schrijf alle resultaten in een lokaal TXT-verslag in Downloads, inclusief
   nulresultaten en twijfelgevallen. Geen rapport in GitHub.

**Alle voorgestelde categorieën zijn niet-bevestigd.** Zelfs een directe
Engelse OFF/Shopify-labelmatch valideert het product niet inhoudelijk. Er wordt
geen GS1-Brick afgeleid of opgeslagen. De proef kan ook niet vaststellen *door
wie* een bestaande GTIN oorspronkelijk werd toegekend; voor een latere,
schrijvende koppeling is dat een afzonderlijk autorisatie- en auditvereiste.

### Wel en niet

| Wel | Uitdrukkelijk niet |
| --- | --- |
| Centrale Catalogus met een bestaande code | ED2-bonartikelen zonder Cataloguscode |
| Exacte OFF-GET bij geldige bestaande GTIN | Product zoeken op een verzonnen barcode of op naam |
| Shopify NL pad als **voorstel** | Vastleggen van GS1-, Artikelgroep- of Producttype-velden |
| Beperkte CBS-vergelijking | CBS-code als officiële productidentificatie |
| Volledige lokale beoordelingstabel | Database-, Docker-, schema-, voorraad- of bonmutaties |

## Werkwijze voor Michiel

1. Download het losse `Inhuis_Taxonomie_Proef6_Catalogus_1klik.cmd`.
2. Dubbelklik op de vertrouwde Windows-ontwikkellaptop. Script gebruikt exact
   vastgepinde GitHub-SHA en reeds draaiende backend, zonder installatie,
   herstart, force of reset. De Norton-vriendelijke CMD bevat geen ingesloten
   PowerShell-/Pythonprogramma.
3. Houd rekening met minstens zes seconden per extra unieke GTIN, plus
   netwerkreactietijd. Het rapport groeit tijdens het opvragen en toont
   `VOORTGANG OFF n/N`; het opdrachtvenster sluit niet vanzelf.
4. Upload uitsluitend
   `Downloads\Inhuis_Taxonomie_Proef6_Catalogus_Resultaat.txt` in ChatGPT.
5. Pas op basis van werkelijke resultaten de brede aggregatieniveaus aan;
   voer daarna een kwaliteitssteekproef uit. Eventuele opslag/migratie alleen
   na nieuw besluit en aparte uitvoerings- en terugvalproef.

## Testbewijs

`python3 -m tools.inhuis_taxonomy_proof6_selftest`: OFF-tagmatching,
NL/EN consistentie, bereide aardappel, ambiguïteit bij melk,
gecombineerde productnamen, read-only databasecontract en afwezigheid ED2-query.
De echte OFF/PostgreSQL-praktijkproef draait alleen op Michiels eigen bestaande
backend; de broncode zelf maakt daar geen schrijfacties.

TEST_LEVEL_PROVISIONAL: L

Reden: standalone diagnostische backendtool met bestaande databaseconnector,
geen runtimewijziging maar fail-closed als onbekend CI-pad.

STYLEGUIDE_IMPACT: none

STYLEGUIDE_REASON: geen gebruikersinterface- of stijlaanpassingen.
