# R7b-27 — closeout summary and R7c recommendation

Status: R7b closeout  
Branch: `sync/local-rezzerv-receipt-basis-v2`  
Scope: documentatie-only

## Doel

Dit document sluit R7b formeel af. R7b was gericht op onderhoudbaarheid van receipt ingestion zonder functionele parserwijzigingen.

Het doel was niet om OCR- of parserkwaliteit te verbeteren, maar om `receipt_service.py` gecontroleerd open te breken en duidelijke modulegrenzen te introduceren.

## R7b uitgangspunten

Tijdens R7b golden de volgende principes:

- geen grote herschrijvingen;
- geen OCR-tuning;
- geen parserkwaliteit wijzigen;
- geen statuslogica wijzigen;
- geen fallbackgedrag wijzigen;
- kleine rollbackbare stappen;
- eerst sanity freezing, daarna extractie;
- geen dode legacycode bewust laten liggen zonder documentatie.

## Belangrijk tussentijds herstel

Tijdens R7b kwam de oude Kassa-categorie `Handmatig` opnieuw terug.

Deze regressie is vóór verdere refactoring hersteld:

- backendstatus defensief opgeschoond;
- `manual`/`Handmatig` gemapt naar `Controle nodig` voor actieve Kassa-statussen;
- statusbadge genormaliseerd;
- Kassa summary cards aangepast naar twee actieve categorieën;
- app-validatie uitgevoerd.

Actieve Kassa-categorieën zijn nu:

- `Gecontroleerd`
- `Controle nodig`

Niet meer:

- `Handmatig`

## Uitgevoerde R7b-stappen

### R7b-16b — parse_decimal sanity freezing

Toegevoegd:

```text
tools/check_r7b16_parse_decimal_sanity.py
```

Doel:

- bestaand `_parse_decimal` gedrag bevriezen vóór extractie.

### R7b-17 — parse_decimal extraction

`_parse_decimal` is uit `receipt_service.py` gehaald en aangesloten op:

```text
backend/app/receipt_ingestion/amounts.py
```

Via import-alias:

```python
parse_decimal as _parse_decimal
```

### R7b-17b — amount sanity alignment

De bestaande amount-helper sanitytest is uitgelijnd op het bevroren R7b-16b gedrag.

### R7b-18 — post amount extraction inventory

Toegevoegd:

```text
docs/architecture/R7b18_post_amount_extraction_helper_inventory.md
```

Conclusie:

- fingerprinthelpers waren de veiligste volgende extractiekandidaat.

### R7b-19 — fingerprint sanity freezing

Toegevoegd:

```text
tools/check_r7b19_fingerprint_helpers_sanity.py
```

Doel:

- fingerprintgedrag bevriezen vóór extractie.

### R7b-20 — fingerprint boundary extraction

Toegevoegd:

```text
backend/app/receipt_ingestion/fingerprints.py
```

Pure fingerprinthelpers zijn uit `receipt_service.py` gehaald.

Niet verplaatst:

- DB-coupled fingerprint lookup;
- deduplicatiequery's;
- repositoryachtige functies.

### R7b-21 — boundary validation checkpoint

Toegevoegd:

```text
docs/architecture/R7b21_receipt_ingestion_boundary_validation.md
```

Vastgelegd:

- amount boundary;
- fingerprint boundary;
- sanitychecks;
- app-validatie;
- Kassa-regressiecheck.

### R7b-22 — amount helper residue inventory

Toegevoegd:

```text
docs/architecture/R7b22_amount_helper_residue_inventory.md
```

Geïnventariseerd:

- `_parse_quantity`
- `_amount_to_float`
- `_price_from_split_parts`

### R7b-23 — amount residue sanity freezing

Toegevoegd:

```text
tools/check_r7b23_amount_residue_sanity.py
```

Doel:

- resterende pure amount-helpersemantiek vastleggen vóór wiring.

### R7b-24 — amount residue wiring

De resterende pure amount helpers zijn via import-aliases aangesloten op:

```text
backend/app/receipt_ingestion/amounts.py
```

### R7b-25 — amount boundary validation

Toegevoegd:

```text
docs/architecture/R7b25_amount_boundary_validation.md
```

Vastgelegd:

- volledige amount-boundary;
- sanitychecks;
- grep-validatie;
- app-validatie.

### R7b-26 — remaining receipt_service responsibility inventory

Toegevoegd:

```text
docs/architecture/R7b26_remaining_receipt_service_responsibility_inventory.md
```

Vastgelegd welke verantwoordelijkheden bewust nog in `receipt_service.py` blijven:

- orchestration;
- DB-coupled deduplicatie;
- OCR-runtime;
- store-specific parsing;
- generic text parsing;
- financial reconciliation;
- discountmatching;
- upload/share/source utilities.

## Bereikte modulegrenzen

Na R7b zijn de volgende boundaries actief:

```text
backend/app/receipt_ingestion/amounts.py
backend/app/receipt_ingestion/fingerprints.py
backend/app/receipt_ingestion/line_classifier.py
backend/app/receipt_ingestion/product_candidate_gateway.py
backend/app/receipt_ingestion/structured_product_gateway.py
backend/app/receipt_ingestion/parser_diagnostics.py
backend/app/receipt_ingestion/parser_debug_serializer.py
backend/app/receipt_ingestion/fallback_policy.py
backend/app/receipt_ingestion/store_specific_router.py
backend/app/receipt_ingestion/generic_text_parser.py
```

## Validatiestatus

Lokaal groen bevestigd tijdens R7b:

```powershell
python tools/check_r7b16_parse_decimal_sanity.py
python tools/check_r7b13b_amount_helpers_sanity_standalone.py
python tools/check_r7b19_fingerprint_helpers_sanity.py
python tools/check_r7b23_amount_residue_sanity.py
```

App-validatie bevestigd:

- Docker Compose start;
- backend start;
- frontend start;
- Kassa opent;
- bonnen kunnen worden ingelezen;
- `Handmatig` komt niet terug als actieve Kassa-categorie.

## Wat bewust niet meer in R7b is gedaan

Niet aangepakt in R7b:

- discountmatching extractie;
- total reconciliation extractie;
- store-specific parserextractie;
- OCR-runtime extractie;
- parserkwaliteit verbeteren;
- statusalgoritme aanpassen;
- fallbackgedrag wijzigen;
- fixturebaseline vernieuwen.

Reden:

Deze onderdelen hebben hogere functionele impact en vragen fixture- of regressietestdekking voordat ze veilig verplaatst of verbeterd kunnen worden.

## R7b conclusie

R7b kan worden gesloten.

De belangrijkste opbrengst is dat `receipt_service.py` nog steeds groot is, maar niet langer een volledig gesloten monoliet is. De service is verder verschoven naar orchestration, terwijl pure helpers voor amounts en fingerprints en ondersteunende parser-boundaries zijn afgesplitst.

R7b heeft daarmee zijn onderhoudbaarheidsdoel bereikt zonder bewust parsergedrag te wijzigen.

## Advies voor R7c

R7c moet niet starten met opnieuw helperextractie zonder testbasis.

Aanbevolen R7c-richting:

```text
R7c — receipt parser regression baseline and fixture governance
```

Doel:

- eerst fixture- en regressiecontrole versterken;
- daarna pas functioneel gevoelige onderdelen aanpakken zoals discountmatching, total reconciliation of store-specific parsers.

## Mogelijke R7c-stappen

### R7c-1 — parser fixture baseline inventory

Inventariseer beschikbare kassabonfixtures, verwachte outputs en ontbrekende coverage.

### R7c-2 — receipt parser regression runner hardening

Maak of versterk een runner die per fixture controleert:

- winkelnaam;
- datum;
- totaalbedrag;
- aantal regels;
- regeltotalen;
- discounttotalen;
- parserdiagnostics.

### R7c-3 — discount/reconciliation risk inventory

Analyseer welke discount- en total helpers veilig testbaar zijn en welke fixtures nodig zijn.

### R7c-4 — store-specific parser boundary proposal

Ontwerp een latere boundary voor winkel- of bron-specifieke parsers zonder directe extractie.

## Aanbevolen eerste opdracht na R7b

Start met:

```text
R7c-1 — parser fixture baseline inventory
```

Niet met:

- directe discount-extractie;
- directe OCR-tuning;
- directe parserverbetering.

## Definitieve status

R7b status: gesloten na validatie van dit document.
