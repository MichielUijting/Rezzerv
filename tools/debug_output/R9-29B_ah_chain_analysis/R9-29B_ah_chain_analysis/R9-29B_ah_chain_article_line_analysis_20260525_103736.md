# R9-29B — AH ketenbrede artikelregel-analyse

Gemaakt: `2026-05-25T10:37:36`

## SSOT-guardrails

- `status_determination`: `not_performed`
- `status_service`: `receipt_status_baseline_service_v4.py`
- `parser_mutated`: `False`
- `ocr_mutated`: `False`
- `database_mutated`: `False`
- `ui_mutated`: `False`
- `baseline_mutated`: `False`

## Batch

- `id`: `None`
- `source_filename`: `supermarkten.zip`
- `total_files`: `14`
- `processed_files`: `14`
- `imported_files`: `14`
- `status`: `completed`
- `created_at`: `None`
- `finished_at`: `None`

## Samenvatting

- `batch_entry_count`: `14`
- `ah_receipt_count`: `4`
- `ah_receipt_ids`: `['366811062c85484c8d54363ea3bd3834', '875370b6731e410b9f67dd7775542e3f', '983c3ce155df4c43940c7a8a4a0ba024', 'c809be56d65742478601f332a063b29c']`
- `failed_criteria_counts_from_status_report`: `{'ARTICLE_COUNT_MISMATCH': 11, 'LINE_SUM_TOTAL_MISMATCH': 10, 'STORE_CHAIN_MISMATCH': 1, 'TOTAL_AMOUNT_MISMATCH': 3}`
- `line_class_counts`: `{'article_candidate': 23, 'quantity_or_multibuy_signal': 1, 'non_article_candidate': 3}`
- `pattern_counts`: `{'non_article_candidates_present': 1}`
- `amount_source_counts`: `{'line_total': 27}`

## AH-bonnen

| Bon | receipt_table_id | Totaal | Status | Verwacht regels | DB-regels | Failed criteria |
|---|---|---:|---|---:|---:|---|
| `AH App 1.pdf` | `366811062c85484c8d54363ea3bd3834` | `5.02` | `review_needed` | `4` | `3` | ARTICLE_COUNT_MISMATCH`, `LINE_SUM_TOTAL_MISMATCH |
| `AH foto 1.pdf` | `875370b6731e410b9f67dd7775542e3f` | `49.27` | `review_needed` | `23` | `22` | ARTICLE_COUNT_MISMATCH`, `LINE_SUM_TOTAL_MISMATCH |
| `AH foto 2.jpeg` | `983c3ce155df4c43940c7a8a4a0ba024` | `8.28` | `approved` | `2` | `2` |  |
| `AH foto 3.jpg` | `c809be56d65742478601f332a063b29c` | `0.0` | `review_needed` | `1` | `0` | STORE_CHAIN_MISMATCH`, `TOTAL_AMOUNT_MISMATCH |

## Detail per AH-bon

### AH App 1.pdf

- `receipt_table_id`: `366811062c85484c8d54363ea3bd3834`
- `total_amount`: `5.02`
- `parse_status`: `review_needed`
- `expected_line_count`: `4`
- `actual_line_count_in_status_report`: `3`
- `db_line_count`: `3`
- `failed_criteria`: `['ARTICLE_COUNT_MISMATCH', 'LINE_SUM_TOTAL_MISMATCH']`
- `status_report_reason`: `Controle nodig: artikelcount wijkt af van baseline; som van artikelregels sluit niet aan op kassabontotaal`
- `classification_counts`: `{'article_candidate': 3}`

| # | Bedrag | Classificatie | Naam / tekst | Reden |
|---:|---:|---|---|---|
| 1 | `1.19` | `article_candidate` | `1 POEDERSUIKER \| 1 POEDERSUIKER \| unmatched` | `has amount and no obvious non-article term` |
| 2 | `0.99` | `article_candidate` | `1 CARE INLEGKR \| 1 CARE INLEGKR \| unmatched` | `has amount and no obvious non-article term` |
| 3 | `2.19` | `article_candidate` | `1 AH POFFERTJE \| 1 AH POFFERTJE \| unmatched` | `has amount and no obvious non-article term` |

### AH foto 1.pdf

- `receipt_table_id`: `875370b6731e410b9f67dd7775542e3f`
- `total_amount`: `49.27`
- `parse_status`: `review_needed`
- `expected_line_count`: `23`
- `actual_line_count_in_status_report`: `22`
- `db_line_count`: `22`
- `failed_criteria`: `['ARTICLE_COUNT_MISMATCH', 'LINE_SUM_TOTAL_MISMATCH']`
- `status_report_reason`: `Controle nodig: artikelcount wijkt af van baseline; som van artikelregels sluit niet aan op kassabontotaal`
- `classification_counts`: `{'article_candidate': 18, 'quantity_or_multibuy_signal': 1, 'non_article_candidate': 3}`

| # | Bedrag | Classificatie | Naam / tekst | Reden |
|---:|---:|---|---|---|
| 1 | `1.3` | `article_candidate` | `1 PREI \| 1 PREI \| unmatched` | `has amount and no obvious non-article term` |
| 2 | `1.98` | `article_candidate` | `2 KOMKOMMER 0,99 \| 2 KOMKOMMER 0,99 \| unmatched` | `has amount and no obvious non-article term` |
| 3 | `2.69` | `article_candidate` | `1 DRUIVEN \| 1 DRUIVEN \| unmatched` | `has amount and no obvious non-article term` |
| 4 | `3.19` | `quantity_or_multibuy_signal` | `0.404KG KIWI GOLD 7,90 \| 0.404KG KIWI GOLD 7,90 \| unmatched` | `quantity/multibuy pattern` |
| 5 | `0.7` | `article_candidate` | `1 WINTERPEEN \| 1 WINTERPEEN \| unmatched` | `has amount and no obvious non-article term` |
| 6 | `2.12` | `article_candidate` | `1 AH GRF ROOKV \| 1 AH GRF ROOKV \| unmatched` | `has amount and no obvious non-article term` |
| 7 | `1.99` | `article_candidate` | `1 VOLK BOLLEN \| 1 VOLK BOLLEN \| unmatched` | `has amount and no obvious non-article term` |
| 8 | `1.35` | `article_candidate` | `1 WALDK HALF \| 1 WALDK HALF \| unmatched` | `has amount and no obvious non-article term` |
| 9 | `2.15` | `article_candidate` | `1 REMIA SAUS \| 1 REMIA SAUS \| unmatched` | `has amount and no obvious non-article term` |
| 10 | `1.59` | `article_candidate` | `1 ZAANS H MAYO \| 1 ZAANS H MAYO \| unmatched` | `has amount and no obvious non-article term` |
| 11 | `1.99` | `article_candidate` | `1 AH MUFFINS \| 1 AH MUFFINS \| unmatched` | `has amount and no obvious non-article term` |
| 12 | `1.65` | `article_candidate` | `1 AH BOUILLON \| 1 AH BOUILLON \| unmatched` | `has amount and no obvious non-article term` |
| 13 | `1.18` | `article_candidate` | `2 AH BOUILLON 0,59 \| 2 AH BOUILLON 0,59 \| unmatched` | `has amount and no obvious non-article term` |
| 14 | `0.69` | `article_candidate` | `1 AH BOUILLON \| 1 AH BOUILLON \| unmatched` | `has amount and no obvious non-article term` |
| 15 | `2.69` | `article_candidate` | `1 KATJA SNOEP \| 1 KATJA SNOEP \| unmatched` | `has amount and no obvious non-article term` |
| 16 | `1.29` | `article_candidate` | `1 AH HV MELK \| 1 AH HV MELK \| unmatched` | `has amount and no obvious non-article term` |
| 17 | `1.19` | `article_candidate` | `1 AH TORTILLA \| 1 AH TORTILLA \| unmatched` | `has amount and no obvious non-article term` |
| 18 | `1.38` | `non_article_candidate` | `2 CHIO CHIPS 0,69 \| 2 CHIO CHIPS 0,69 \| unmatched` | `payment/total/header/footer term` |
| 19 | `1.17` | `non_article_candidate` | `3 AH CHIPS 0,39 \| 3 AH CHIPS 0,39 \| unmatched` | `payment/total/header/footer term` |
| 20 | `0.69` | `non_article_candidate` | `1 CHIO CHIPS \| 1 CHIO CHIPS \| unmatched` | `payment/total/header/footer term` |
| 21 | `9.38` | `article_candidate` | `2 AH MALBEC 4,69 \| 2 AH MALBEC 4,69 \| unmatched` | `has amount and no obvious non-article term` |
| 22 | `0.99` | `article_candidate` | `1 TUINERWTEN \| 1 TUINERWTEN \| unmatched` | `has amount and no obvious non-article term` |

### AH foto 2.jpeg

- `receipt_table_id`: `983c3ce155df4c43940c7a8a4a0ba024`
- `total_amount`: `8.28`
- `parse_status`: `approved`
- `expected_line_count`: `2`
- `actual_line_count_in_status_report`: `2`
- `db_line_count`: `2`
- `failed_criteria`: `[]`
- `status_report_reason`: `Gecontroleerd: winkelketen, totaalbedrag, artikelcount en regelsom voldoen aan de PO-norm.`
- `classification_counts`: `{'article_candidate': 2}`

| # | Bedrag | Classificatie | Naam / tekst | Reden |
|---:|---:|---|---|---|
| 1 | `6.99` | `article_candidate` | `T AH M GEHAKT \| T AH M GEHAKT \| unmatched` | `has amount and no obvious non-article term` |
| 2 | `1.29` | `article_candidate` | `1 SOEPGR BASIS \| 1 SOEPGR BASIS \| unmatched` | `has amount and no obvious non-article term` |

### AH foto 3.jpg

- `receipt_table_id`: `c809be56d65742478601f332a063b29c`
- `total_amount`: `0.0`
- `parse_status`: `review_needed`
- `expected_line_count`: `1`
- `actual_line_count_in_status_report`: `1`
- `db_line_count`: `0`
- `failed_criteria`: `['STORE_CHAIN_MISMATCH', 'TOTAL_AMOUNT_MISMATCH']`
- `status_report_reason`: `Controle nodig: winkelketen wijkt af van baseline; totaalbedrag wijkt af van baseline`
- `classification_counts`: `{}`

| # | Bedrag | Classificatie | Naam / tekst | Reden |
|---:|---:|---|---|---|

## Gezamenlijke AH-foutpatronen

- `non_article_candidates_present`: `1`

## Aanbevolen oplossingsvolgorde

### 1. Status report mapping

- Actie: Use summary.failed_criteria_counts and details[].receipt_table_id/details[].failed_criteria/details[].expected_line_count from the Swagger status report as read-only diagnostics.
- Guardrail: No status logic changes; status remains governed by receipt_status_baseline_service_v4.py.

### 4. Regression

- Actie: After every AH parser change, run the complete 14-receipt baseline and verify that previously Gecontroleerd receipts do not degrade.
- Guardrail: No change in status service or PO status norm.

## Besluit

Gebruik dit rapport als input voor een aparte AH-profielpatch. Deze analyse heeft niets gewijzigd.
