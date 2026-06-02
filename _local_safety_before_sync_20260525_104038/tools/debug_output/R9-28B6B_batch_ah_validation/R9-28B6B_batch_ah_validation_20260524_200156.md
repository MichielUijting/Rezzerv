# R9-28B6B — Batchvalidatie alle AH-bonnen

Gemaakt: `2026-05-24T20:01:56`

## SSOT-compliance

- `status_determination`: `not_performed`
- `status_service`: `receipt_status_baseline_service_v4.py`
- `parse_status_used_as_truth`: `False`
- `parser_mutated`: `False`
- `ocr_mutated`: `False`
- `database_mutated`: `False`
- `baseline_mutated`: `False`
- `ui_touched`: `False`
- `diagnostics_promoted_to_parser`: `False`

## Guardrail tegen bon-specifieke regels

- `filename_specific_rules_allowed`: `False`
- `member_specific_rules_allowed`: `False`
- `hardcoded_receipt_ids_allowed`: `False`
- `member_regex_used_only_for_batch_selection`: `(?i)(^|[/\\])(AH|Albert|Albert\s*Heijn)[^/\\]*\.(jpg|jpeg|png|bmp|tif|tiff|webp)$`
- `note`: `The same R9-28B5/R9-28B6 generic pipeline is executed for every selected AH member.`

## Batchsamenvatting

- `ah_member_count`: `2`
- `passed_count`: `1`
- `failed_or_suspicious_count`: `1`
- `failure_types`: `{'zero_amount_article_candidate': 1}`
- `total_reconstructed_articles`: `4`
- `total_blocked_non_article_items`: `68`

## Per AH-bon

| Member | Pass | Artikelen | Som | Suspicious | OCR items | Boxes |
|---|---:|---:|---:|---:|---:|---:|
| `AH foto 2.jpeg` | `True` | `2` | `8.28` | `0` | `69` | `69` |
| `AH foto 3.jpg` | `False` | `2` | `5.4` | `1` | `70` | `70` |

## Gereconstrueerde artikelen per bon

### `AH foto 2.jpeg`
- `AH M GEHAKT` — `6,99`
- `SOEPGR BASIS` — `1,29`

### `AH foto 3.jpg`
- `CHAUDF WATER` — `5,40`
- `AH SANDWICH` — `0,00`

Suspicious findings:
- `zero_amount_article_candidate`

## Vervolg

Use batch-level recurring failure patterns only. Do not patch per receipt. If correction is needed, implement one generic AH rule and rerun this batch.
