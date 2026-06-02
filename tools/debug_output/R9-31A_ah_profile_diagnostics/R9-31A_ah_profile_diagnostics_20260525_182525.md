# R9-31A — AH Receipt Profile diagnostics

Gemaakt: `2026-05-25T18:25:25`

## SSOT-guardrails
- `status_determination`: `not_performed`
- `status_service`: `receipt_status_baseline_service_v4.py`
- `parser_mutated`: `False`
- `ocr_mutated`: `False`
- `database_mutated`: `False`
- `ui_mutated`: `False`
- `baseline_mutated`: `False`
- `filename_runtime_branching`: `False`

## Samenvatting
- `receipt_count`: `14`
- `ah_profile_receipt_count`: `4`
- `ah_profile_receipt_ids`: `['99a997e160984227832aa909c200f9c4', '566cbedff8c24d139f4af6a0bc2bbf06', '4df96d85fbdc4250b5d7277206355a7f', 'f7cc3cb968034e5996a01f5b102fa2bf']`

## None

- `receipt_table_id`: `99a997e160984227832aa909c200f9c4`
- `store_name`: `Albert Heijn`
- `detection`: `{'chain_id': 'ah', 'display_name': 'Albert Heijn', 'confidence': 'none', 'score': 0, 'evidence': [], 'conflicts': []}`
- `summary`: `{'line_count': 3, 'class_counts': {'article_candidate': 3}, 'section_counts': {'article_block': 2, 'header': 1}, 'article_candidate_count': 3, 'discount_candidate_count': 0, 'payment_candidate_count': 0, 'total_candidate_count': 0}`

| # | Sectie | Classificatie | Bedrag | Tekst | Reden |
|---:|---|---|---:|---|---|
| 1 | `article_block` | `article_candidate` | `1.19` | `1 POEDERSUIKER 1.19` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 2 | `article_block` | `article_candidate` | `0.99` | `1 CARE INLEGKR 0.99` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 3 | `header` | `article_candidate` | `2.19` | `1 AH POFFERTJE 2.19` | `quantity or leading number plus label plus amount; no hard payment/total marker` |

## None

- `receipt_table_id`: `566cbedff8c24d139f4af6a0bc2bbf06`
- `store_name`: `Albert Heijn`
- `detection`: `{'chain_id': 'ah', 'display_name': 'Albert Heijn', 'confidence': 'none', 'score': 0, 'evidence': [], 'conflicts': []}`
- `summary`: `{'line_count': 22, 'class_counts': {'header': 1, 'article_candidate': 20, 'noise': 1}, 'section_counts': {'header': 10, 'article_block': 12}, 'article_candidate_count': 20, 'discount_candidate_count': 0, 'payment_candidate_count': 0, 'total_candidate_count': 0}`

| # | Sectie | Classificatie | Bedrag | Tekst | Reden |
|---:|---|---|---:|---|---|
| 1 | `header` | `header` | `None` | `1 PREI 1.3` | `header or store context line` |
| 2 | `article_block` | `article_candidate` | `1.98` | `2 KOMKOMMER 0,99 1.98` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 3 | `article_block` | `article_candidate` | `2.69` | `1 DRUIVEN 2.69` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 4 | `article_block` | `article_candidate` | `3.19` | `0.404KG KIWI GOLD 7,90 3.19` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 5 | `article_block` | `noise` | `None` | `1 WINTERPEEN 0.7` | `no AH article or fiscal marker` |
| 6 | `header` | `article_candidate` | `2.12` | `1 AH GRF ROOKV 2.12` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 7 | `article_block` | `article_candidate` | `1.99` | `1 VOLK BOLLEN 1.99` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 8 | `article_block` | `article_candidate` | `1.35` | `1 WALDK HALF 1.35` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 9 | `article_block` | `article_candidate` | `2.15` | `1 REMIA SAUS 2.15` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 10 | `article_block` | `article_candidate` | `1.59` | `1 ZAANS H MAYO 1.59` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 11 | `header` | `article_candidate` | `1.99` | `1 AH MUFFINS 1.99` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 12 | `header` | `article_candidate` | `1.65` | `1 AH BOUILLON 1.65` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 13 | `header` | `article_candidate` | `1.18` | `2 AH BOUILLON 0,59 1.18` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 14 | `header` | `article_candidate` | `0.69` | `1 AH BOUILLON 0.69` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 15 | `article_block` | `article_candidate` | `2.69` | `1 KATJA SNOEP 2.69` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 16 | `header` | `article_candidate` | `1.29` | `1 AH HV MELK 1.29` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 17 | `header` | `article_candidate` | `1.19` | `1 AH TORTILLA 1.19` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 18 | `article_block` | `article_candidate` | `1.38` | `2 CHIO CHIPS 0,69 1.38` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 19 | `header` | `article_candidate` | `1.17` | `3 AH CHIPS 0,39 1.17` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 20 | `article_block` | `article_candidate` | `0.69` | `1 CHIO CHIPS 0.69` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 21 | `header` | `article_candidate` | `9.38` | `2 AH MALBEC 4,69 9.38` | `quantity or leading number plus label plus amount; no hard payment/total marker` |
| 22 | `article_block` | `article_candidate` | `0.99` | `1 TUINERWTEN 0.99` | `quantity or leading number plus label plus amount; no hard payment/total marker` |

## None

- `receipt_table_id`: `4df96d85fbdc4250b5d7277206355a7f`
- `store_name`: `Albert Heijn`
- `detection`: `{'chain_id': 'ah', 'display_name': 'Albert Heijn', 'confidence': 'none', 'score': 0, 'evidence': [], 'conflicts': []}`
- `summary`: `{'line_count': 2, 'class_counts': {'article_candidate': 2}, 'section_counts': {'header': 1, 'article_block': 1}, 'article_candidate_count': 2, 'discount_candidate_count': 0, 'payment_candidate_count': 0, 'total_candidate_count': 0}`

| # | Sectie | Classificatie | Bedrag | Tekst | Reden |
|---:|---|---|---:|---|---|
| 1 | `header` | `article_candidate` | `6.99` | `T AH M GEHAKT 6.99` | `label plus amount; no hard payment/total marker` |
| 2 | `article_block` | `article_candidate` | `1.29` | `1 SOEPGR BASIS 1.29` | `quantity or leading number plus label plus amount; no hard payment/total marker` |

## None

- `receipt_table_id`: `f7cc3cb968034e5996a01f5b102fa2bf`
- `store_name`: `Albert Heijn`
- `detection`: `{'chain_id': 'ah', 'display_name': 'Albert Heijn', 'confidence': 'none', 'score': 0, 'evidence': [], 'conflicts': []}`
- `summary`: `{'line_count': 0, 'class_counts': {}, 'section_counts': {}, 'article_candidate_count': 0, 'discount_candidate_count': 0, 'payment_candidate_count': 0, 'total_candidate_count': 0}`

| # | Sectie | Classificatie | Bedrag | Tekst | Reden |
|---:|---|---|---:|---|---|

## Besluit
Deze analyse is read-only en vormt input voor R9-31B.