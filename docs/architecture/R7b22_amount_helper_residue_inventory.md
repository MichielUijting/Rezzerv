# R7b-22 — amount helper residue inventory

Status: analyse-only  
Branch: `sync/local-rezzerv-receipt-basis-v2`  
Scope: onderhoudbaarheid receipt ingestion  
Productiecode gewijzigd: nee

## Doel

Inventariseren welke lokale amount-gerelateerde helpers na R7b-17 nog in `backend/app/services/receipt_service.py` staan en bepalen welke veilig later via `backend/app/receipt_ingestion/amounts.py` aangesloten kunnen worden.

Deze stap wijzigt geen parsergedrag, OCR-flow, statuslogica, fallbackgedrag of databaseflow.

## Context

R7b-17 heeft `_parse_decimal` uit `receipt_service.py` verwijderd en aangesloten via:

```python
from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal
```

De amount-boundary `backend/app/receipt_ingestion/amounts.py` bevat inmiddels:

- `parse_decimal`
- `parse_quantity`
- `amount_to_float`
- `price_from_split_parts`

## Gevonden lokale resthelpers

### 1. `_parse_quantity`

Locatie:

```text
backend/app/services/receipt_service.py
```

Gedrag:

- accepteert `str | None`;
- vervangt komma door punt;
- verwijdert niet-numerieke tekens behalve `-` en `.`;
- retourneert `Decimal` of `None`.

Afhankelijkheden:

- `Decimal`
- `InvalidOperation`
- `ValueError`
- `re`

Observatie:

Deze helper is vrijwel identiek aan `parse_quantity` in `receipt_ingestion/amounts.py`.

Risico:

Laag tot middel. De helper wordt gebruikt in productregelparsering en append-gateway callbacks. Een semantisch verschil kan artikelregels of hoeveelheden beïnvloeden, maar de helper zelf is puur en statusneutraal.

Advies:

Geschikt voor vervolgstap, maar eerst sanity freezing uitvoeren.

### 2. `_amount_to_float`

Locatie:

```text
backend/app/services/receipt_service.py
```

Gedrag:

- `Decimal | None` naar `float | None`;
- behoudt `None` semantiek.

Afhankelijkheden:

- geen bijzondere dependencies.

Observatie:

Deze helper is inhoudelijk identiek aan `amount_to_float` in `receipt_ingestion/amounts.py`.

Risico:

Laag. Veel callsites gebruiken de helper bij serialisatie naar DB/API-achtige payloads, maar het gedrag is triviaal.

Advies:

Geschikt voor snelle aansluiting via import-alias, mits eerst sanitycheck aanwezig is.

### 3. `_price_from_split_parts`

Locatie:

```text
backend/app/services/receipt_service.py`
```

Gedrag:

- bouwt een `Decimal` uit losse euro- en centdelen;
- gebruikt `int(euros)` en `int(cents):02d`;
- retourneert `Decimal('x.yy')` of `None`.

Afhankelijkheden:

- `Decimal`

Observatie:

Deze helper komt functioneel overeen met `price_from_split_parts` in `receipt_ingestion/amounts.py`.

Belangrijke context:

De helper wordt vooral geraakt door store-specifieke parsing, met name Picnic/flattened email-achtige prijsfragmenten. Daardoor is het technisch klein maar parseroutput-gevoelig.

Risico:

Middel. Niet vanwege complexiteit, maar omdat de helper dichtbij store-specifieke email parsing ligt.

Advies:

Meenemen na sanity freezing, niet blind vervangen.

## Lokale directe amountlogica buiten helpers

Naast de drie resthelpers staat er nog directe financiële logica in `receipt_service.py`, onder andere rond:

- `Decimal(str(...))`
- `quantize(Decimal('0.01'))`
- `line_total`
- `discount_amount`
- `unit_price`
- totaalcontrole en discountverrekening

Deze logica zit onder andere in:

- `determine_final_parse_status`
- `_receipt_line_financials`
- `_totals_match_receipt_lines`
- `_discount_or_free_total_zero_case`
- store-specifieke parsers zoals Action/Gamma/Hornbach/Lidl/Picnic/Bol

Advies:

Niet meenemen in de eerstvolgende stap. Dit raakt parserkwaliteit, total reconciliation of statusafleiding en moet apart worden voorbereid met fixtures.

## Callsite-inschatting

Te controleren in de vervolgstap met lokale `Select-String`:

```powershell
Select-String -Path backend\app\services\receipt_service.py -Pattern "_parse_quantity\(" | Measure-Object
Select-String -Path backend\app\services\receipt_service.py -Pattern "_amount_to_float\(" | Measure-Object
Select-String -Path backend\app\services\receipt_service.py -Pattern "_price_from_split_parts\(" | Measure-Object
```

Interpretatie:

- `_parse_quantity`: verwacht meerdere callsites in generic line parsing en sparse parsing;
- `_amount_to_float`: verwacht veel callsites in product candidates, result serialization en DB writes;
- `_price_from_split_parts`: verwacht beperkte callsites, vooral Picnic/e-mail flattening.

## Aanbevolen vervolgstap

R7b-23 — amount residue sanity freezing

Doel:

- standalone sanitytest toevoegen voor:
  - `parse_quantity`
  - `amount_to_float`
  - `price_from_split_parts`
- exact huidig lokaal helpergedrag bevriezen;
- geen productiecode wijzigen.

Voorgesteld testbestand:

```text
tools/check_r7b23_amount_residue_sanity.py
```

Minimale testgevallen:

### parse_quantity

- `1` -> `Decimal('1')`
- `1,5` -> `Decimal('1.5')`
- `1.5` -> `Decimal('1.5')`
- `2 kg` -> `Decimal('2')`
- `abc` -> `None`
- `None` -> `None`

### amount_to_float

- `Decimal('1.23')` -> `1.23`
- `Decimal('0.00')` -> `0.0`
- `None` -> `None`

### price_from_split_parts

- `('1', '23')` -> `Decimal('1.23')`
- `('0', '05')` -> `Decimal('0.05')`
- `('12', '5')` -> `Decimal('12.05')`
- `(None, '23')` -> `None`
- `('1', None)` -> `None`
- `('abc', '23')` -> `None`

Daarna pas:

R7b-24 — wire amount residue helpers through `receipt_ingestion/amounts.py`

## Niet aanbevolen in R7b-23/R7b-24

Niet meenemen:

- `_receipt_line_financials`
- `_totals_match_receipt_lines`
- `_discount_or_free_total_zero_case`
- discount matching helpers
- store-specific parser rewrites
- statuslogica in `determine_final_parse_status`

## Conclusie

De veiligste volgende stap is niet opnieuw extractie, maar eerst sanity freezing van de resterende pure amount helpers.

Daarna kunnen `_parse_quantity`, `_amount_to_float` en mogelijk `_price_from_split_parts` met import-aliases worden aangesloten op de bestaande `amounts.py` boundary.
