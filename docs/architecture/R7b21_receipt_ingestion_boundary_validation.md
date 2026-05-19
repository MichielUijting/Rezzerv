# R7b-21 — receipt ingestion boundary validation

Status: validatie-checkpoint  
Branch: `sync/local-rezzerv-receipt-basis-v2`  
Referentiecommit: `77ae199`  
Scope: documentatie-only

## Doel

Dit document legt het stabiele checkpoint vast na de onderhoudbaarheidsstappen rond amount- en fingerprint-boundaries.

Er zijn in deze stap geen productiecodewijzigingen gedaan.

## Afgeronde stappen

### R7b-17 — amount boundary

`parse_decimal` is uit `backend/app/services/receipt_service.py` gehaald en aangesloten via:

```python
from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal
```

De lokale helperdefinitie `_parse_decimal(...)` staat niet meer in `receipt_service.py`.

### R7b-17b — sanity alignment

De standalone amount-helper sanitytest is uitgelijnd op het bevroren R7b-16b gedrag.

### R7b-18 — post amount extraction helper inventory

Toegevoegd:

```text
docs/architecture/R7b18_post_amount_extraction_helper_inventory.md
```

Conclusie: fingerprinthelpers waren de veiligste volgende extractiekandidaat.

### R7b-19 — fingerprint sanity freezing

Toegevoegd:

```text
tools/check_r7b19_fingerprint_helpers_sanity.py
```

Doel: het bestaande fingerprintgedrag vastleggen vóór extractie.

### R7b-20 — fingerprint boundary

Toegevoegd:

```text
backend/app/receipt_ingestion/fingerprints.py
```

De pure fingerprinthelpers zijn uit `receipt_service.py` gehaald en staan nu alleen nog in `fingerprints.py`.

Niet verplaatst:

- `find_existing_receipt_by_fingerprint`
- `_fingerprint_from_stored_receipt`

Reden: deze functies bevatten DB-/repository-coupling en blijven voorlopig in `receipt_service.py`.

## Lokale validatie

De volgende checks zijn lokaal uitgevoerd en groen bevonden:

```powershell
python tools/check_r7b16_parse_decimal_sanity.py
python tools/check_r7b13b_amount_helpers_sanity_standalone.py
python tools/check_r7b19_fingerprint_helpers_sanity.py
```

Resultaten:

- R7b-16b parse decimal sanity check passed.
- R7b-17 standalone amount helper sanity check passed.
- R7b-19 fingerprint helper sanity check passed.

Opmerking: de R7b-19 sanitytest toont een `datetime.utcnow()` deprecation warning. Deze warning is niet blokkerend, omdat het script bewust het bestaande gedrag bevriest.

## Grep-validatie

Uitgevoerde controle:

```powershell
git grep -n "def _normalize_fingerprint_text\|def _build_receipt_fingerprint" -- backend/app/services/receipt_service.py backend/app/receipt_ingestion/fingerprints.py
```

Uitkomst:

De helperdefinities staan alleen nog in:

```text
backend/app/receipt_ingestion/fingerprints.py
```

Niet meer in:

```text
backend/app/services/receipt_service.py
```

## App-startcheck

Lokaal bevestigd:

- backend start via Docker Compose;
- frontend start via Docker Compose;
- Kassa opent;
- bonnen kunnen opnieuw worden ingelezen;
- de categorie `Handmatig` blijft weg;
- de app werkt na R7b-20.

## Architectuurstatus

De volgende boundaries zijn nu actief:

- `amounts.py`
- `fingerprints.py`
- `line_classifier.py`
- `product_candidate_gateway.py`
- `structured_product_gateway.py`
- `parser_diagnostics.py`
- `parser_debug_serializer.py`
- `fallback_policy.py`
- `store_specific_router.py`
- `generic_text_parser.py`

`receipt_service.py` is nog groot, maar de monoliet is verder opengebroken en bevat minder pure helperlogica.

## Aanbevolen vervolgstap

Niet direct discount- of total-reconciliation extractie uitvoeren.

Aanbevolen volgende onderhoudbaarheidsstap:

```text
R7b-22 — amount helper residue inventory
```

Doel:

- inventariseren welke lokale amount helpers nog in `receipt_service.py` staan;
- bepalen of `_parse_quantity`, `_amount_to_float` en `_price_from_split_parts` veilig via de bestaande `amounts.py` boundary kunnen worden aangesloten;
- eerst analyseren, daarna pas wijzigen.

Niet doen in R7b-22:

- geen OCR-verbetering;
- geen parserkwaliteit aanpassen;
- geen statuslogica wijzigen;
- geen discountmatching wijzigen;
- geen total-reconciliation extractie.
