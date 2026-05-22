# R9-01 — Receipt service responsibility inventory

Status: uitgevoerd als inventarisatie
Scope: `backend/app/services/receipt_service.py`
Runtime-impact: geen
Database-impact: geen
Parser/OCR-impact: geen

## Doel

Na de route-governance cleanup is de volgende onderhoudbaarheidsstap het verder ontleden van `receipt_service.py`.

Deze stap brengt in kaart welke verantwoordelijkheden nog in dit servicebestand zitten en in welke volgorde ze veilig kunnen worden geëxtraheerd.

## Observatie

`receipt_service.py` is nog steeds een samengestelde service met meerdere verantwoordelijkheden:

1. bron- en bestandsafhandeling;
2. opslag en deduplicatie;
3. tekstextractie;
4. OCR-fallbacks;
5. tekstnormalisatie;
6. winkelherkenning;
7. datum- en totaalbedragdetectie;
8. artikelregelparsing;
9. discountmatching;
10. fallback- en uitzonderingslogica;
11. parse-resultaatclassificatie;
12. parserdiagnostiek;
13. databasepersistency.

Er zijn al modules ontstaan onder `app.receipt_ingestion`, maar de orchestration en veel domeinheuristiek zitten nog in `receipt_service.py`.

## Bestaande extracties die al zichtbaar zijn

| Module | Rol |
|---|---|
| `app.receipt_ingestion.line_classifier` | classificatie van tekstregels |
| `app.receipt_ingestion.product_candidate_gateway` | uniforme append van productkandidaten |
| `app.receipt_ingestion.structured_product_gateway` | append van gestructureerde productregels |
| `app.receipt_ingestion.parser_diagnostics` | samenvatting parserdiagnostiek |
| `app.receipt_ingestion.parser_debug_serializer` | debugpayload |
| `app.receipt_ingestion.preprocessing.safe_rotation` | veilige rotatie/preprocessing |
| `app.receipt_ingestion.amounts` | bedrag-, prijs- en quantity-parsing |
| `app.receipt_ingestion.fingerprints` | fingerprinting en plausibiliteitschecks |

## Nog aanwezige verantwoordelijkheden in `receipt_service.py`

### 1. Bestands- en brondetectie

Voorbeelden:

- extensies en MIME-detectie;
- share-source helpers;
- bestandsnaamnormalisatie;
- HTML/email/PDF/image bronafhandeling.

Advies:

- voorlopig laten staan;
- later naar `receipt_sources` of `receipt_io` verplaatsen.

### 2. Dedupe en fingerprint orchestration

Voorbeelden:

- bestaande receipt lookup;
- fingerprintvergelijking;
- duplicaatmarkering;
- soft-delete bij duplicaten.

Status:

- fingerprint-hulpfuncties zijn deels geëxtraheerd;
- database-orchestratie zit nog in `receipt_service.py`.

Advies:

- later naar `receipt_dedupe_service.py` verplaatsen.

### 3. Parse-statusbepaling

Voorbeeld:

- `determine_final_parse_status` bepaalt database-status op basis van parse-resultaat.

Let op:

- statusbepaling blijft bestuurlijk gevoelig;
- niet mengen met POC-parserstatus of testdiagnostiek.

Advies:

- nu niet wijzigen;
- later expliciet koppelen aan SSOT status baseline.

### 4. Tekstextractie en OCR-routes

Voorbeelden:

- PDF tekstextractie;
- OCRmyPDF fallback;
- PaddleOCR fallback;
- image OCR normalisatie;
- grouping van OCR-fragmenten naar regels.

Advies:

- aparte extractiekandidaat:
  `backend/app/receipt_ingestion/ocr_routes.py`
  of
  `backend/app/receipt_ingestion/text_extraction.py`.

### 5. Tekstnormalisatie

Voorbeelden:

- PDF tekst preprocessing;
- HTML naar tekst;
- regelnormalisatie;
- accent stripping;
- OCR-regelgroepering.

Advies:

- verplaatsen naar `text_normalization.py`.

### 6. Store/date/total detectie

Voorbeelden:

- winkelherkenning uit tekst en bestandsnaam;
- filiaalherkenning;
- aankoopdatumdetectie;
- totaalbedragdetectie.

Advies:

- dit is een goede eerste echte extractiestap na R9-01;
- voorgestelde module:
  `backend/app/receipt_ingestion/header_parser.py`.

### 7. Artikelregelparsing

Voorbeelden:

- item label detection;
- detail-only lines;
- quantity-first en label-first patronen;
- pending-line merge;
- non-product filters;
- sparse fallback parsing.

Advies:

- niet als eerste verplaatsen;
- dit is risicovol voor parsingkwaliteit;
- eerst header parsing isoleren.

### 8. Discountmatching

Voorbeelden:

- discount-line extractie;
- discount label normalisatie;
- matchscore;
- attachen van korting aan productregels.

Advies:

- na header parser als tweede of derde extractiestap;
- module:
  `discount_parser.py`.

### 9. Store-specifieke heuristiek

Voorbeelden:

- Aldi context en VAT/payment filters;
- Jumbo foto 3 fallback;
- allowlist voor sparse fallback.

Advies:

- niet uitbreiden in `receipt_service.py`;
- later onder store profiles plaatsen:
  `receipt_ingestion/profiles/*`.

### 10. Parse orchestration

Voorbeeld:

- `_parse_result_from_text_lines` combineert header, lines, discounts, fallbacks, status en diagnostics.

Advies:

- uiteindelijk wordt dit de orchestrationlaag;
- nu nog niet herschrijven;
- eerst afhankelijke pure functies isoleren.

## Risicoanalyse

| Gebied | Risico bij extractie | Toelichting |
|---|---:|---|
| Header parsing | Laag-middel | Goed testbaar; beperkt effect op regels |
| Discount parsing | Middel | Kan totalen en status beïnvloeden |
| Artikelregelparsing | Hoog | Direct effect op kassabonregels |
| OCR routes | Middel-hoog | Runtime-afhankelijkheden en fallbackgedrag |
| Dedupe | Middel | Kan zichtbaarheid/verwijderstatus beïnvloeden |
| Final status | Hoog | Raakt PO-status en baseline-governance |

## Aanbevolen vervolgvolgorde

### R9-02 — Header parser extractie

Verplaats winkel-, filiaal-, datum- en totaalbedragdetectie naar:

```text
backend/app/receipt_ingestion/header_parser.py
```

Te verplaatsen functies:

```text
_store_from_text
_looks_like_store_branch_line
_store_branch_from_lines
_purchase_at_from_lines
_total_amount_from_lines
```

Acceptatie:

- import vanuit `receipt_service.py`;
- functienamen kunnen voorlopig identiek blijven;
- geen wijziging in gedrag;
- geen databasewijziging;
- bestaande kassabonstatussen blijven gelijk.

### R9-03 — Discount parser extractie

Verplaats discount helpers naar:

```text
backend/app/receipt_ingestion/discount_parser.py
```

### R9-04 — Non-product filters en line guards

Verplaats labelguards naar:

```text
backend/app/receipt_ingestion/line_filters.py
```

### R9-05 — OCR/text extraction split

Verplaats OCR- en tekstextractieroutes naar aparte modules.

### R9-06 — Orchestrator afslanken

Maak `receipt_service.py` primair verantwoordelijk voor:

- bron ophalen;
- parser aanroepen;
- resultaat opslaan;
- database-orchestratie.

## Stopregels

Stop direct als:

1. parsingstatus van bestaande testbonnen verandert;
2. aantal regels per testbon verandert;
3. store-name detectie verandert;
4. total_amount detectie verandert;
5. kassabon-import faalt;
6. route-governance wijzigt onverwacht;
7. PO-statusbaseline verandert zonder expliciete wijziging.

## R9-01 conclusie

De meest logische eerste onderhoudbaarheidsstap is niet artikelregelparsing, maar header parsing extractie.

Daarmee wordt een relatief begrensd deel uit `receipt_service.py` gehaald zonder direct de kwetsbaarste line parser te raken.

## Concrete vervolgopdracht

R9-02: extraheer header parsing naar `backend/app/receipt_ingestion/header_parser.py` zonder gedragswijziging.
