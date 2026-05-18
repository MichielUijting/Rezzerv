# R7b-10 — Inventaris pure helperfuncties voor extractie uit receipt_service.py

## Status

Analyse-opdracht. Geen codewijziging.

## Doel

Bepalen welke helperfuncties uit `backend/app/services/receipt_service.py` veilig verplaatst kunnen worden naar `backend/app/receipt_ingestion/`, zonder parsergedrag, statuslogica of databasegedrag te wijzigen.

Deze stap sluit aan op:

- R3: product candidate gateway;
- R4: parser diagnostics;
- R5: parser debug serializer;
- R7b-4/R7b-7: store-specific router boundary;
- R7b-5/R7b-6: fallback policy boundary;
- R7b-8/R7b-9: generic text parser boundary.

## Extractiecriterium

Een helper is kandidaat voor verplaatsing als deze:

1. geen database gebruikt;
2. geen filesystem/OCR-side effects heeft;
3. geen statusbeslissing voor Kassa neemt;
4. deterministisch is op basis van input;
5. eenvoudig met unit tests te dekken is;
6. geen circulaire imports veroorzaakt.

## Niet verplaatsen in deze fase

Niet verplaatsen in R7b-11/R7b-12:

- `ingest_receipt(...)`;
- `reparse_receipt(...)`;
- database helpers;
- OCR engine state zoals Paddle/Tesseract initialisatie;
- statuscontract of PO-normlogica;
- store-specific parsers zelf.

## Categorie A — Zeer veilige pure helpers

Deze kunnen als eerste naar een utilitymodule, omdat ze weinig afhankelijkheden hebben en breed herbruikbaar zijn.

Voorgestelde module:

```text
backend/app/receipt_ingestion/normalization.py
```

Kandidaten:

| Helper | Functie | Risico | Advies |
|---|---|---:|---|
| `sanitize_filename` | veilige bestandsnaam maken | laag | verplaatsen naar `normalization.py` of `storage_names.py` |
| `_normalize_text_lines` | ruwe tekst naar regels | laag | verplaatsen naar `normalization.py` |
| `_preprocess_pdf_text` | eenvoudige PDF-tekstnormalisatie | laag/middel | verplaatsen naar `normalization.py`, maar eerst tests toevoegen |
| `_normalize_store_specific_text` | tekstnormalisatie voor store parsers | laag/middel | verplaatsen naar `normalization.py` |
| `_clean_receipt_label` | labelopschoning | middel | verplaatsen na snapshottests op bestaande bonregels |

Aanbevolen eerste implementatie:

```text
R7b-11 — verplaats _normalize_text_lines naar receipt_ingestion/normalization.py
```

Waarom:

- zeer klein;
- geen status;
- geen database;
- veel gebruikt;
- makkelijk te controleren.

## Categorie B — Bedrag- en quantity parsing

Voorgestelde module:

```text
backend/app/receipt_ingestion/amounts.py
```

Kandidaten:

| Helper | Functie | Risico | Advies |
|---|---|---:|---|
| `_parse_decimal` | bedragstring naar Decimal | middel | verplaatsen met unit tests |
| `_amount_to_float` | Decimal naar float/None | laag | samen met bedragen verplaatsen |
| `_parse_quantity` | hoeveelheid parseren | laag/middel | samen met bedragen verplaatsen |
| `_price_from_split_parts` | euros/cents combineren | laag | samen met bedragen verplaatsen |
| `_is_plausible_total_amount` | bedrag plausibility | middel | pas na tests verplaatsen |

Advies:

Eerst tests toevoegen voor komma/punt/negatieve bedragen voordat `_parse_decimal` wordt verplaatst.

## Categorie C — Datumherkenning

Voorgestelde module:

```text
backend/app/receipt_ingestion/dates.py
```

Kandidaten:

| Helper | Functie | Risico | Advies |
|---|---|---:|---|
| `_parse_dutch_textual_date` | Nederlandse tekstdatum | laag/middel | verplaatsen met tests |
| `_purchase_at_from_lines` | aankoopdatum uit OCR-regels | middel/hoog | later verplaatsen, afhankelijk van parserfixtures |
| `_is_plausible_purchase_at` | plausibility datum | laag/middel | samen met datumhelpers verplaatsen |

Advies:

Niet als eerste. Datumherkenning is functioneel gevoelig.

## Categorie D — Store detectie en branch detectie

Voorgestelde module:

```text
backend/app/receipt_ingestion/store_detection.py
```

Kandidaten:

| Helper | Functie | Risico | Advies |
|---|---|---:|---|
| `_store_from_text` | winkelnaam detecteren | hoog | pas verplaatsen met regressietests per winkel |
| `_store_branch_from_lines` | vestiging/adres detecteren | hoog | later verplaatsen |
| `_looks_like_store_branch_line` | adresregel herkennen | middel | alleen samen met branchdetectie |

Advies:

Nog niet verplaatsen. Deze helpers beïnvloeden PO/statusindruk sterk.

## Categorie E — Product-/niet-product filtering

Voorgestelde module:

```text
backend/app/receipt_ingestion/product_filtering.py
```

Kandidaten:

| Helper | Functie | Risico | Advies |
|---|---|---:|---|
| `_looks_like_non_product_receipt_label` | bonkop/totaalregels uitsluiten | hoog | verplaatsen na fixturetests |
| `_filter_non_product_receipt_lines` | productlijnen filteren | hoog | later, met regression diff |
| `_classify_receipt_text_line` wrapper | classifier adapter | middel | later, omdat gateway gebruikt classifier |

Advies:

Belangrijk, maar niet vroeg verplaatsen. Fout hierin raakt artikelregels direct.

## Categorie F — Totalen, korting en reconciliatie

Voorgestelde module:

```text
backend/app/receipt_ingestion/reconciliation/
  totals.py
  discounts.py
```

Kandidaten:

| Helper | Functie | Risico | Advies |
|---|---|---:|---|
| `_total_amount_from_lines` | totaalbedrag uit OCR | hoog | pas met fixtures |
| `_totals_match_receipt_lines` | totaalcontrole | hoog | later |
| `_discount_or_free_total_zero_case` | nul/actie-case | hoog | later |
| `_extract_discount_entries` | kortingregels detecteren | hoog | later |
| `_apply_discount_entries` | korting toepassen op regels | hoog | later |

Advies:

Niet verplaatsen vóórdat er regressietestfixtures zijn. Deze helpers beïnvloeden kwaliteitsdiagnose en statusindruk.

## Categorie G — Fingerprinting en duplicate matching

Voorgestelde module:

```text
backend/app/receipt_ingestion/fingerprints.py
```

Kandidaten:

| Helper | Functie | Risico | Advies |
|---|---|---:|---|
| `sha256_hex` | hash file bytes | laag | kan verplaatst worden |
| `_build_receipt_fingerprint` | parser fingerprint | middel | later verplaatsen |
| `build_receipt_fingerprint_from_parse_result` | parse result fingerprint | middel | later |
| `find_existing_receipt_by_fingerprint` | DB duplicate lookup | hoog | niet in pure helperfase |

Advies:

`sha256_hex` kan vroeg, maar duplicate lookup blijft repository/persistence.

## Categorie H — OCR/file processing helpers

Niet in pure helperfase.

Voorbeelden:

- `_extract_pdf_text`;
- `_ocr_pdf_text_with_ocrmypdf`;
- `_ocr_image_text_with_paddle`;
- `_ocr_image_text_with_tesseract`;
- `_convert_webp_to_png_bytes`.

Reden:

- externe libraries;
- file/engine state;
- performancegevoelig;
- integratietests nodig.

## Aanbevolen volgorde na R7b-10

### R7b-11 — normalisatieboundary starten

Verplaats alleen:

```text
_normalize_text_lines
```

naar:

```text
backend/app/receipt_ingestion/normalization.py
```

Acceptatie:

- alle bestaande aanroepen blijven werken via import;
- output identiek;
- backend start;
- Kassa-lijst/detail werkt;
- bekende bon importeerbaar.

### R7b-12 — bedraghelpers voorbereiden met tests

Maak tests/sanitychecks voor:

- `1,23`;
- `1.23`;
- `€ 1,23`;
- negatieve bedragen;
- lege waarde;
- euros/cents split.

Nog geen verplaatsing zonder tests.

### R7b-13 — `_amount_to_float` en `_parse_quantity` verplaatsen

Na testbasis.

### R7b-14 — `_parse_decimal` verplaatsen

Pas na bedragtests.

## Acceptatiecriteria voor helperextractie

1. Geen statuslogica geraakt.
2. Geen parserconfidence gewijzigd.
3. Geen fallbackgedrag gewijzigd.
4. Geen databasequery gewijzigd.
5. Iedere verplaatste helper heeft één duidelijke nieuwe eigenaarmodule.
6. `receipt_service.py` importeert helper, maar behoudt voorlopig public API.
7. Elke stap is rollbackbaar via één patchhelper.

## Conclusie

De veiligste volgende stap is:

```text
R7b-11 — verplaats _normalize_text_lines naar receipt_ingestion/normalization.py
```

Dit is klein, puur, statusvrij en sluit logisch aan op de eerder geïntroduceerde parser boundaries.
