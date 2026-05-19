# R7b-18 — post amount extraction helper inventory

Status: analyse-only  
Scope: onderhoudbaarheid receipt ingestion  
Branch: `sync/local-rezzerv-receipt-basis-v2`

## Aanleiding

R7b-17 heeft `_parse_decimal` uit `backend/app/services/receipt_service.py` gehaald en via een import-alias aangesloten op `backend/app/receipt_ingestion/amounts.py`.

Daarmee is de amount-boundary aangezet, maar `receipt_service.py` bevat nog meerdere kleine helpers. Deze inventaris bepaalt welke helpers later veilig moduleerbaar zijn zonder functionele parserwijziging.

## Randvoorwaarden

Niet doen in deze stap:

- geen productiecode wijzigen;
- geen OCR/parsingkwaliteit wijzigen;
- geen statuslogica wijzigen;
- geen fallbackgedrag wijzigen;
- geen databaseflow wijzigen.

## Huidige relevante modulegrenzen

Aanwezige receipt-ingestion boundaries:

- `line_classifier.py`
- `product_candidate_gateway.py`
- `structured_product_gateway.py`
- `parser_diagnostics.py`
- `parser_debug_serializer.py`
- `amounts.py`

`receipt_service.py` importeert deze boundaries al bovenin en gebruikt `parse_decimal` inmiddels via `parse_decimal as _parse_decimal`.

## Helpercategorieën in receipt_service.py

### A. Pure text/file helpers — laag risico

Kandidaten:

- `sanitize_filename`
- `sanitize_share_context`
- `share_source_label_for_context`
- `detect_mime_type`
- `sha256_hex`
- `_html_to_text`

Observatie:

Deze helpers zijn grotendeels pure functies. Ze hebben geen DB-state en geen parserstatus-impact. Wel worden enkele helpers buiten pure receipt parsing gebruikt, bijvoorbeeld upload/share/importflows.

Advies:

- Nog niet meteen verplaatsen naar `receipt_ingestion`.
- Eventueel later naar een generieke utilitymodule, bijvoorbeeld `backend/app/receipt_ingestion/file_utils.py` of breder `backend/app/utils/files.py`.
- Eerst callsites inventariseren buiten `receipt_service.py`.

Risico: laag tot middel, afhankelijk van upload/sharegebruik.

### B. Fingerprint/plausibility helpers — geschikte volgende kandidaat

Kandidaten:

- `_normalize_fingerprint_text`
- `_is_plausible_purchase_at`
- `_is_plausible_total_amount`
- `_build_receipt_fingerprint`
- `build_receipt_fingerprint_from_parse_result`
- `_build_receipt_fingerprint_from_db_row`
- `find_existing_receipt_by_fingerprint`

Observatie:

De eerste vijf helpers zijn grotendeels pure logica rond receipt identity en deduplicatie. `find_existing_receipt_by_fingerprint` bevat DB-coupling en moet voorlopig blijven staan of apart worden behandeld.

Advies:

- Volgende veilige extractiestap kan zijn: alleen pure fingerprint helpers naar `backend/app/receipt_ingestion/fingerprints.py`.
- DB-functie `find_existing_receipt_by_fingerprint` voorlopig niet meenemen.
- Vooraf sanitytest toevoegen voor fingerprint-output op vaste input.

Risico: middel, want deduplicatie en bestaande-bon-detectie hangen hiervan af.

### C. Amount/financial helpers — deels al gemoduleerd, resterend voorzichtig behandelen

Al geëxtraheerd of aangesloten:

- `_parse_decimal` via `receipt_ingestion.amounts.parse_decimal`
- eerdere amount helpers in `amounts.py`

Resterende financiële helpers in `receipt_service.py`:

- `_line_decimal_total`
- `_discount_decimal_total`
- `_receipt_line_financials`
- `_totals_match_receipt_lines`
- `_discount_or_free_total_zero_case`

Observatie:

Deze helpers zijn inhoudelijk klein, maar raken totaalcontrole, kwaliteitsscore en parserdiagnose. Ze zijn minder geschikt als directe volgende extractie dan fingerprint helpers.

Advies:

- Niet als eerstvolgende stap.
- Eerst extra sanity/fixturetests rond regel-som, discount-som en totaalcontrole toevoegen.

Risico: middel tot hoog.

### D. Discount matching helpers — moduleerbaar maar functioneel gevoelig

Kandidaten:

- `_strip_accents`
- `_normalize_discount_match_text`
- `_extract_discount_entries`
- `_discount_match_score`
- `_apply_discount_entries`

Observatie:

Deze helpers zijn grotendeels lokaal en logisch samenhangend. Ze bepalen echter hoe kortingsregels aan productregels worden gekoppeld en kunnen daardoor parseroutput wijzigen als extractie niet exact gebeurt.

Advies:

- Alleen later als aparte stap, bijvoorbeeld `receipt_ingestion/discounts.py`.
- Vooraf fixturetest toevoegen met minimaal één bonus/kortingbon.

Risico: hoog voor parseroutput, laag voor statuslogica.

### E. Product line parsing helpers — niet nu

Kandidaten:

- `_extract_savings_action_lines`
- `_clean_receipt_label`
- `_looks_like_non_receipt`
- `_looks_like_non_product_receipt_label`
- `_classify_receipt_text_line` wrappers/compatibility helpers

Observatie:

Deze helpers zitten dicht tegen feitelijke parserkwaliteit aan. Extractie kan technisch mogelijk zijn, maar de kans op subtiele parserwijziging is groter.

Advies:

- Niet in de eerstvolgende onderhoudbaarheidsstap.
- Eerst verdere testdekking en parser fixture alignment.

Risico: hoog.

## Aanbevolen vervolgstap

R7b-19 — fingerprint helper preparation

Doel:

- geen productiecode wijzigen;
- sanitytest toevoegen voor fingerprint helpers;
- vaste inputs en outputs vastleggen vóór extractie.

Voorstel testbestand:

`tools/check_r7b19_fingerprint_helpers_sanity.py`

Te bevriezen gedrag:

- normalisatie van winkelnaam;
- normalisatie van regellabel;
- datumformattering in fingerprint;
- totaalbedragformattering;
- fingerprintopbouw met maximaal eerste 12 regels;
- gedrag bij ongeldige datum of totaalbedrag.

Daarna pas:

R7b-20 — extract pure fingerprint helpers naar `backend/app/receipt_ingestion/fingerprints.py`.

## Niet aanbevolen als eerstvolgende stap

Niet direct doen:

- discount extractie;
- totals/reconciliation extractie;
- product line parser extractie;
- DB-fingerprintfunctie verplaatsen;
- OCR-route opschonen.

## Conclusie

De veiligste volgende onderhoudbaarheidslijn is fingerprinting, niet discounting of financial reconciliation.

R7b-19 moet daarom eerst de pure fingerprint-helpersemantiek vastleggen. Pas daarna kan R7b-20 de helpers verplaatsen naar een aparte receipt-ingestion boundary.
