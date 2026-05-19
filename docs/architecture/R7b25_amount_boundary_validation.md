# R7b-25 — amount boundary validation

Status: validatie-checkpoint  
Branch: `sync/local-rezzerv-receipt-basis-v2`  
Scope: documentatie-only

## Doel

Dit document legt het checkpoint vast na R7b-24: de amount-boundary is nu compleet aangesloten voor de pure amount helpers die eerder nog lokaal in `receipt_service.py` stonden.

Deze stap wijzigt geen productiecode, parsergedrag, OCR-flow, statuslogica, fallbackgedrag of databaseflow.

## Boundaries na R7b-24

De centrale amount-boundary is:

```text
backend/app/receipt_ingestion/amounts.py
```

Deze module bevat nu de actieve helperdefinities voor:

- `parse_decimal`
- `parse_quantity`
- `amount_to_float`
- `price_from_split_parts`

## Aansluiting vanuit receipt_service.py

`backend/app/services/receipt_service.py` gebruikt de amount-boundary via import-aliases:

```python
from app.receipt_ingestion.amounts import (
    amount_to_float as _amount_to_float,
    parse_decimal as _parse_decimal,
    parse_quantity as _parse_quantity,
    price_from_split_parts as _price_from_split_parts,
)
```

Daardoor konden bestaande callsites intact blijven zonder functionele wijziging.

## Afgeronde relevante stappen

### R7b-17 — parse_decimal boundary

`_parse_decimal` is uit `receipt_service.py` gehaald en aangesloten op:

```text
receipt_ingestion.amounts.parse_decimal
```

### R7b-17b — sanity alignment

De amount-helper sanitytest is uitgelijnd op het bevroren R7b-16b gedrag.

### R7b-22 — amount residue inventory

Vastgelegd welke lokale resthelpers nog aanwezig waren:

- `_parse_quantity`
- `_amount_to_float`
- `_price_from_split_parts`

Conclusie: alle drie waren geschikte kandidaten voor wiring via de bestaande `amounts.py` boundary, mits eerst sanity freezing plaatsvond.

### R7b-23 — amount residue sanity freezing

Toegevoegd:

```text
tools/check_r7b23_amount_residue_sanity.py
```

Deze test bevriest het bestaande gedrag van:

- `_parse_quantity`
- `_amount_to_float`
- `_price_from_split_parts`

### R7b-24 — amount residue wiring

De lokale helperdefinities zijn verwijderd uit `receipt_service.py` en vervangen door import-aliases naar `amounts.py`.

## Lokale sanitychecks

De volgende checks horen groen te zijn na R7b-24:

```powershell
python tools/check_r7b16_parse_decimal_sanity.py
python tools/check_r7b13b_amount_helpers_sanity_standalone.py
python tools/check_r7b23_amount_residue_sanity.py
```

Beoogde resultaten:

- R7b-16b parse decimal sanity check passed.
- R7b-17 standalone amount helper sanity check passed.
- R7b-23 amount residue sanity check passed.

## Grep-validatie

Te gebruiken controle:

```powershell
git grep -n "def _parse_decimal\|def _parse_quantity\|def _amount_to_float\|def _price_from_split_parts" -- backend/app/services/receipt_service.py backend/app/receipt_ingestion/amounts.py
```

Verwachting:

- geen helperdefinities meer in `backend/app/services/receipt_service.py`;
- definities alleen nog in `backend/app/receipt_ingestion/amounts.py`.

Let op: in `amounts.py` heten de helpers zonder underscore:

- `parse_decimal`
- `parse_quantity`
- `amount_to_float`
- `price_from_split_parts`

## App-check

Lokaal bevestigd als onderdeel van de R7b-validaties:

- backend start via Docker Compose;
- frontend start via Docker Compose;
- Kassa opent;
- bonnen kunnen worden ingelezen;
- categorie `Handmatig` blijft weg.

## Architectuurimpact

`receipt_service.py` behoudt bestaande callsites via aliases, maar de pure amount-helperdefinities zijn verplaatst naar een dedicated boundary.

Dit verlaagt de hoeveelheid pure helperlogica in de orchestration/service-laag zonder parsergedrag te wijzigen.

## Niet meegenomen

Bewust niet aangepakt in deze stap:

- discountmatching;
- total reconciliation;
- `_receipt_line_financials`;
- `_totals_match_receipt_lines`;
- `_discount_or_free_total_zero_case`;
- store-specific parser rewrites;
- OCR-tuning.

Deze onderdelen hebben hogere functionele impact en horen niet meer in deze kleine wiring-stap.

## Aanbevolen vervolgstap

R7b-26 — remaining receipt_service responsibility inventory

Doel:

- vastleggen welke verantwoordelijkheden bewust nog in `receipt_service.py` blijven;
- expliciet scheiden tussen orchestration, DB-coupling, OCR-runtime, parser-routing, financial reconciliation en store-specific parsing;
- bepalen of R7b daarna kan worden gesloten.
