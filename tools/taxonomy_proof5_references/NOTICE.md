# Herkomst en gebruik – taxonomieproef 5

Deze bestandskopieën zijn **uitsluitend referentiegegevens voor een read-only
haalbaarheidsproef**. Geen artikelkoppelingen, productgroepen of GS1-codes
worden hieruit automatisch opgeslagen.

## Shopify Standard Product Taxonomy

- Bron: https://github.com/Shopify/product-taxonomy
- Versie: `v2026-08`, Nederlandstalig `categories.nl.json.gz`.
- Download: https://github.com/Shopify/product-taxonomy/releases/download/v2026-08/categories.nl.json.gz
- SHA256 origineel: `35dad4fdf7a00ca91e3b3170739565ca1bb552622d00d02da365c7c71357306a`
- Afgeleide referentie: `shopify_2026_08_nl.json.gz`, uitsluitend categorie-id,
  Nederlandse naam, officieel hiërarchisch pad en parent-id (geen attributen).
- Licentie: MIT; auteur `Copyright (c) Shopify`; volledige tekst hieronder.
- Dit bestand levert **een indeling**, geen barcode-naar-categorie-database.

### MIT License

Copyright (c) Shopify

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Aanvullende Shopify EN-voedselindex voor proef 6

- Dezelfde vastgepinde Shopify-release `v2026-08`, géén nieuwe taxonomievariant.
- Officiële Engelse bron: https://github.com/Shopify/product-taxonomy/releases/download/v2026-08/categories.en.json.gz
- SHA256 van originele Engelse bron: `bb400431cf6c28cc1ddad9f2d9c5c3c918db94454ebeb68238ffa8740ee89d05`.
- Afgeleide `shopify_2026_08_en_food.json.gz`: 764 voedsel-/drankencategorieën,
  alleen ID en Engelse naam. Deze koppelen via dezelfde officiële ID aan de
  bestaande Nederlandstalige categoriepaden.
- Generator: `tools/inhuis_taxonomy_proof6_build_en_reference.py`.
- Hergebruik onder dezelfde Shopify MIT-voorwaarden als hierboven.
- Geen barcode-index; OFF-databankdata worden niet in deze bron opgenomen.

## CBS ECOICOPv2

- Bron: Centraal Bureau voor de Statistiek, *De ECOICOPv2 indeling*,
  gepubliceerd 12 februari 2026.
- https://www.cbs.nl/nl-nl/longread/diversen/2026/de-ecoicopv2-indeling/bijlage
- Officiële bijlage: https://www.cbs.nl/-/media/_excel/2026/04/bijlageecoicopv2indeling.xlsx
- SHA256 origineel: `6871458274be87aa0126eab1bf334365502438f5e976845df8e5c28cdf95858f`
- Afgeleid bestand: `cbs_ecoicop_v2_2026.json`, alleen 440 codes en namen
  uit werkblad `1-ECOICOPv2`.
- CBS hergebruik van webcontent: CC BY 4.0, naamsvermelding aan CBS.
- ECOICOPv2 is oorspronkelijk een **consumptie-/bestedingsindeling**;
  deze proef doet geen officiële CBS-producttoekenning.

## OFF

Open Food Facts wordt niet overgenomen in dit project: slechts maximaal zes
read-only barcode-opvragen uit de bestaande InHuis-service, met beperkte
wachttijd; categoriegegevens blijven in het lokale resultaat. OFF-databank is
ODbL (vereist aparte toetsing van eventuele productiedatahergebruikvoorwaarden).

## Herbouw

Voer met de twee vastgepinde, originele bestanden de afzonderlijke ontwikkeltool
`tools/inhuis_taxonomy_proof5_build_references.py` uit. Geen downloads nodig
voor gebruik van de meegeleverde proef op Windows.
