# R9-29B — AH ketenbrede artikelregel-analyse

Gemaakt: `2026-05-25T08:06:15`

## SSOT-guardrails

- `status_determination`: `not_performed`
- `status_service`: `receipt_status_baseline_service_v4.py`
- `parser_mutated`: `False`
- `ocr_mutated`: `False`
- `database_mutated`: `False`
- `ui_mutated`: `False`
- `baseline_mutated`: `False`

## Batch

- `id`: `b029599a-c962-49f1-9144-a00a7eb75092`
- `source_filename`: `supermarkten.zip`
- `total_files`: `14`
- `processed_files`: `14`
- `imported_files`: `14`
- `status`: `completed`
- `created_at`: `2026-05-24 22:06:47`
- `finished_at`: `2026-05-24T22:10:23.086446`

## Samenvatting

- `batch_entry_count`: `14`
- `ah_receipt_count`: `4`
- `ah_receipt_ids`: `['1bebee81dae04b71a47dddc31af0de5a', '390d917fae9f473c883967758b27eee4', '71388c521649416db3b91d1c632ed437', 'c5484e2485ce46b3b59abf2174a44bba']`
- `failed_criteria_counts_from_status_report`: `{}`
- `line_class_counts`: `{'article_candidate': 28, 'quantity_or_multibuy_signal': 1, 'non_article_candidate': 1}`
- `pattern_counts`: `{'non_article_candidates_present': 1}`
- `amount_source_counts`: `{'line_total': 30}`

## AH-bonnen

| Bon | receipt_table_id | Totaal | Status | Verwacht regels | DB-regels | Failed criteria |
|---|---|---:|---|---:|---:|---|
| `AH App 1.pdf` | `1bebee81dae04b71a47dddc31af0de5a` | `5.02` | `review_needed` | `None` | `3` | `` |
| `AH foto 1.pdf` | `390d917fae9f473c883967758b27eee4` | `49.27` | `review_needed` | `None` | `22` | `` |
| `AH foto 2.jpeg` | `71388c521649416db3b91d1c632ed437` | `8.28` | `approved` | `None` | `2` | `` |
| `AH foto 3.jpg` | `c5484e2485ce46b3b59abf2174a44bba` | `5.40` | `review_needed` | `None` | `3` | `` |

## Detail per AH-bon

### AH App 1.pdf

- `receipt_table_id`: `1bebee81dae04b71a47dddc31af0de5a`
- `total_amount`: `5.02`
- `parse_status`: `review_needed`
- `expected_line_count`: `None`
- `db_line_count`: `3`
- `status_report_reason`: `None`
- `classification_counts`: `{'article_candidate': 3}`

| # | Bedrag | Classificatie | Naam / tekst | Reden |
|---:|---:|---|---|---|
| 1 | `1.19` | `article_candidate` | `1 POEDERSUIKER \| 1 POEDERSUIKER \| unmatched` | `has amount and no obvious non-article term` |
| 2 | `0.99` | `article_candidate` | `1 CARE INLEGKR \| 1 CARE INLEGKR \| unmatched` | `has amount and no obvious non-article term` |
| 3 | `2.19` | `article_candidate` | `1 AH POFFERTJE \| 1 AH POFFERTJE \| unmatched` | `has amount and no obvious non-article term` |

### AH foto 1.pdf

- `receipt_table_id`: `390d917fae9f473c883967758b27eee4`
- `total_amount`: `49.27`
- `parse_status`: `review_needed`
- `expected_line_count`: `None`
- `db_line_count`: `22`
- `status_report_reason`: `None`
- `classification_counts`: `{'article_candidate': 21, 'quantity_or_multibuy_signal': 1}`

| # | Bedrag | Classificatie | Naam / tekst | Reden |
|---:|---:|---|---|---|
| 1 | `1.30` | `article_candidate` | `1 PREI \| 1 PREI \| unmatched` | `has amount and no obvious non-article term` |
| 2 | `1.98` | `article_candidate` | `2 KOMKOMMER 0,99 \| 2 KOMKOMMER 0,99 \| unmatched` | `has amount and no obvious non-article term` |
| 3 | `2.69` | `article_candidate` | `1 DRUIVEN \| 1 DRUIVEN \| unmatched` | `has amount and no obvious non-article term` |
| 4 | `3.19` | `quantity_or_multibuy_signal` | `0.404KG KIWI GOLD 7,90 \| 0.404KG KIWI GOLD 7,90 \| unmatched` | `quantity/multibuy pattern` |
| 5 | `0.70` | `article_candidate` | `1 WINTERPEEN \| 1 WINTERPEEN \| unmatched` | `has amount and no obvious non-article term` |
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
| 18 | `1.38` | `article_candidate` | `2 CHIO CHIPS 0,69 \| 2 CHIO CHIPS 0,69 \| unmatched` | `has amount and no obvious non-article term` |
| 19 | `1.17` | `article_candidate` | `3 AH CHIPS 0,39 \| 3 AH CHIPS 0,39 \| unmatched` | `has amount and no obvious non-article term` |
| 20 | `0.69` | `article_candidate` | `1 CHIO CHIPS \| 1 CHIO CHIPS \| unmatched` | `has amount and no obvious non-article term` |
| 21 | `9.38` | `article_candidate` | `2 AH MALBEC 4,69 \| 2 AH MALBEC 4,69 \| unmatched` | `has amount and no obvious non-article term` |
| 22 | `0.99` | `article_candidate` | `1 TUINERWTEN \| 1 TUINERWTEN \| unmatched` | `has amount and no obvious non-article term` |

### AH foto 2.jpeg

- `receipt_table_id`: `71388c521649416db3b91d1c632ed437`
- `total_amount`: `8.28`
- `parse_status`: `approved`
- `expected_line_count`: `None`
- `db_line_count`: `2`
- `status_report_reason`: `None`
- `classification_counts`: `{'article_candidate': 2}`

| # | Bedrag | Classificatie | Naam / tekst | Reden |
|---:|---:|---|---|---|
| 1 | `6.99` | `article_candidate` | `T AH M GEHAKT \| T AH M GEHAKT \| unmatched` | `has amount and no obvious non-article term` |
| 2 | `1.29` | `article_candidate` | `T SOEPGR BASIS \| T SOEPGR BASIS \| unmatched` | `has amount and no obvious non-article term` |

### AH foto 3.jpg

- `receipt_table_id`: `c5484e2485ce46b3b59abf2174a44bba`
- `total_amount`: `5.40`
- `parse_status`: `review_needed`
- `expected_line_count`: `None`
- `db_line_count`: `3`
- `status_report_reason`: `None`
- `classification_counts`: `{'article_candidate': 2, 'non_article_candidate': 1}`

| # | Bedrag | Classificatie | Naam / tekst | Reden |
|---:|---:|---|---|---|
| 1 | `3.60` | `article_candidate` | `OMSCHRIJVING 1,80 \| OMSCHRIJVING 1,80 \| unmatched` | `has amount and no obvious non-article term` |
| 2 | `5.40` | `article_candidate` | `AANTAL CHAUDF WATER AH SANDWICH \| AANTAL CHAUDF WATER AH SANDWICH \| unmatched` | `has amount and no obvious non-article term` |
| 3 | `0.45` | `non_article_candidate` | `Leesmethode NFC Chip OVER \| Leesmethode NFC Chip OVER \| unmatched` | `payment/total/header/footer term` |

## Gezamenlijke AH-foutpatronen

- `non_article_candidates_present`: `1`

## Aanbevolen oplossingsvolgorde

### 4. Regression

- Actie: Na elke AH-parserwijziging volledige 14-bonnen baseline draaien en controleren dat eerder Gecontroleerd niet onbedoeld degradeert.
- Guardrail: Geen wijziging in statusservice of PO-statusnorm.

## Besluit

Gebruik dit rapport als input voor een aparte AH-profielpatch. Deze analyse heeft niets gewijzigd.
