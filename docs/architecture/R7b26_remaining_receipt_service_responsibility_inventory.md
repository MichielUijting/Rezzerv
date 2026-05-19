# R7b-26 — remaining receipt_service responsibility inventory

Status: analyse-only / afsluitende inventaris  
Branch: `sync/local-rezzerv-receipt-basis-v2`  
Scope: documentatie-only

## Doel

Dit document legt vast welke verantwoordelijkheden na R7b-17 t/m R7b-25 bewust nog in `backend/app/services/receipt_service.py` blijven.

R7b was gericht op onderhoudbaarheid en modulegrenzen, niet op parserkwaliteit. Daarom is het doel niet om `receipt_service.py` volledig leeg te trekken, maar om de monoliet gecontroleerd open te breken en veilige boundaries te introduceren.

## Reeds afgesplitste boundaries

De volgende receipt-ingestion boundaries bestaan inmiddels en worden actief gebruikt:

- `backend/app/receipt_ingestion/amounts.py`
- `backend/app/receipt_ingestion/fingerprints.py`
- `backend/app/receipt_ingestion/line_classifier.py`
- `backend/app/receipt_ingestion/product_candidate_gateway.py`
- `backend/app/receipt_ingestion/structured_product_gateway.py`
- `backend/app/receipt_ingestion/parser_diagnostics.py`
- `backend/app/receipt_ingestion/parser_debug_serializer.py`
- `backend/app/receipt_ingestion/fallback_policy.py`
- `backend/app/receipt_ingestion/store_specific_router.py`
- `backend/app/receipt_ingestion/generic_text_parser.py`

Hiermee zijn onder andere de volgende helpercategorieën uit `receipt_service.py` gehaald of via boundary-aliases aangesloten:

- decimal amount parsing;
- quantity parsing;
- amount-to-float conversie;
- split euro/cent parsing;
- fingerprint text normalization;
- plausibility checks voor purchase date en total amount;
- fingerprint stringopbouw;
- product append gateways;
- structured product append gateways;
- parserdiagnostics en debug serializer.

## Verantwoordelijkheden die bewust nog in receipt_service.py blijven

### 1. Orchestration van receipt ingestion

Voorbeelden:

- `ingest_receipt`
- `parse_receipt_content`
- `reparse_receipt`
- `repair_receipts_for_household`
- `scan_receipt_source`

Waarom blijft dit voorlopig staan:

- deze functies verbinden opslag, parsing, databasewrites, duplicate checks en responseopbouw;
- ze zijn de feitelijke orchestrationlaag;
- verder opsplitsen vereist eerst een expliciet service/repository ontwerp.

Advies:

- behouden in `receipt_service.py` tot een toekomstige R7c/R8-stap;
- niet verder opsplitsen binnen R7b.

Risico bij verplaatsen: hoog.

### 2. DB-coupled deduplicatie en repositorylogica

Voorbeelden:

- `find_existing_receipt_by_fingerprint`
- `_fingerprint_from_stored_receipt`
- `_load_line_groups`
- `_column_exists`
- `dedupe_receipts_for_household`

Waarom blijft dit voorlopig staan:

- deze functies gebruiken SQLAlchemy/SQL-statements en database-structuur;
- ze zijn geen pure fingerprinthelpers;
- verplaatsen naar `fingerprints.py` zou die pure boundary vervuilen.

Advies:

- later eventueel naar `receipt_repository.py` of `receipt_deduplication_service.py`;
- niet in R7b.

Risico bij verplaatsen: middel tot hoog.

### 3. OCR-runtime en documentextractie

Voorbeelden:

- `_extract_pdf_text`
- `_ocr_pdf_text_with_ocrmypdf`
- `_ocr_image_text_with_paddle`
- `_ocr_image_text_with_tesseract`
- `_get_paddle_ocr`
- `_group_paddle_texts_to_lines`
- `_normalize_paddle_collection`
- `_extract_payload_from_paddle_item`

Waarom blijft dit voorlopig staan:

- deze functies hebben runtime dependencies zoals Tesseract, PaddleOCR, OCRmyPDF, pypdf en PIL;
- gedrag kan per lokale installatie verschillen;
- verplaatsing moet gepaard gaan met aparte OCR-runtime tests.

Advies:

- toekomstige aparte boundary: `receipt_ingestion/ocr_runtime.py`;
- pas oppakken in een aparte OCR-onderhoudbaarheidsserie.

Risico bij verplaatsen: hoog.

### 4. Store- en source-specifieke parsing

Voorbeelden:

- `_parse_action_pdf_result`
- `_parse_gamma_pdf_result`
- `_parse_hornbach_pdf_result`
- `_parse_lidl_invoice_pdf_result`
- `_parse_bol_email_result`
- `_parse_picnic_email_result`
- `_parse_picnic_flattened_blocks`
- `_parse_store_specific_result`

Waarom blijft dit voorlopig staan:

- deze functies bepalen concrete parseroutput;
- ze zijn sterk gekoppeld aan fixturegedrag en winkel-specifieke interpretatie;
- extractie zonder uitgebreide fixturetests kan parserkwaliteit veranderen.

Advies:

- niet meer binnen R7b aanpakken;
- toekomstige stap kan store parsers per winkelprofiel of parsermodule scheiden.

Risico bij verplaatsen: hoog.

### 5. Generic text parsing en productregelconstructie

Voorbeelden:

- `_parse_result_from_text_lines`
- `_extract_receipt_lines`
- `_extract_sparse_receipt_lines`
- `_extract_savings_action_lines`
- `_classify_receipt_text_line` wrapper
- `_should_skip_receipt_line`
- `_looks_like_non_product_receipt_label`
- `_filter_non_product_receipt_lines`

Waarom blijft dit voorlopig staan:

- hoewel een boundary `generic_text_parser.py` bestaat, zitten nog veel concrete parserhelpers in `receipt_service.py`;
- deze functies raken artikelherkenning, labels, hoeveelheden, line totals en fallbackgedrag;
- verdere extractie vereist fixture-gedreven regression coverage.

Advies:

- niet in R7b verder verplaatsen;
- eerst parser fixture baseline en outputvergelijking versterken.

Risico bij verplaatsen: hoog.

### 6. Financial reconciliation en discountmatching

Voorbeelden:

- `_receipt_line_financials`
- `_totals_match_receipt_lines`
- `_discount_or_free_total_zero_case`
- `_extract_discount_entries`
- `_discount_match_score`
- `_apply_discount_entries`
- `_normalize_discount_match_text`
- `_strip_accents`

Waarom blijft dit voorlopig staan:

- deze functies beïnvloeden totaalcontrole, discountverrekening, parserkwaliteit en reviewstatus;
- subtiele verschillen kunnen bonnen verschuiven tussen parsed/review_needed of total mismatch;
- dit vereist fixturetests met kortingsbonnen en totaalcontrole.

Advies:

- niet binnen R7b;
- toekomstige aparte serie: discount/reconciliation hardening.

Risico bij verplaatsen: hoog.

### 7. Upload/share/source utilities

Voorbeelden:

- `sanitize_filename`
- `sanitize_share_context`
- `share_source_label_for_context`
- `ensure_share_receipt_source`
- `detect_mime_type`
- `sha256_hex`
- `_store_raw_file`

Waarom blijft dit voorlopig staan:

- deels generieke utilities, maar gebruikt in ingestion orchestration en databaseflows;
- verplaatsen heeft weinig waarde zolang orchestration in `receipt_service.py` blijft.

Advies:

- pas opsplitsen wanneer upload/source orchestration apart wordt ontworpen.

Risico bij verplaatsen: laag tot middel, maar lage prioriteit.

## Wat R7b heeft bereikt

R7b heeft niet geprobeerd om `receipt_service.py` volledig klein te maken. Wel is bereikt dat:

- pure amountlogica uit de service is gehaald;
- pure fingerprintlogica uit de service is gehaald;
- product appendpaden via gateways lopen;
- parserdiagnostics en debug serialisatie buiten de service staan;
- fallback policy en store routing boundaries bestaan;
- sanitytests bestaan vóór/na extractie;
- de `Handmatig`-regressie is opgespoord en opgelost voordat verder werd gerefactord.

## Criteria voor sluiten van R7b

R7b kan inhoudelijk worden gesloten als het volgende klopt:

- branch staat clean;
- R7b-16b, R7b-17, R7b-19, R7b-20, R7b-23 en R7b-24 checks zijn groen;
- app start via Docker Compose;
- Kassa opent;
- bonnen kunnen worden ingelezen;
- `Handmatig` komt niet terug als actieve Kassa-categorie;
- open resterende verantwoordelijkheden zijn gedocumenteerd als bewuste restscope.

## Aanbevolen afsluitende stap

R7b-27 — closeout summary and R7c recommendation

Doel:

- R7b formeel afsluiten;
- korte samenvatting maken van alle uitgevoerde stappen;
- expliciet vastleggen wat niet meer in R7b wordt gedaan;
- voorstel doen voor R7c.

## Voorgestelde R7c-richting

R7c zou niet opnieuw helperextractie zonder testbasis moeten zijn. De meest logische routes zijn:

1. Parser fixture baseline versterken voor winkelbonnen;
2. Discount/reconciliation hardening voorbereiden;
3. Store-specific parser extraction voorbereiden;
4. OCR-runtime boundary voorbereiden.

Advies:

Start R7c met analyse en fixture/baseline-versterking, niet met directe parserwijzigingen.
