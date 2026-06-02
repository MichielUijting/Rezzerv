# R9-28B6C3 — Resource-safe AH-selectie via bestaande winkelherkenning

Gemaakt: `2026-05-24T20:23:07`

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

## Guardrails

- `existing_store_detection_used`: `True`
- `filename_based_chain_classification_allowed`: `False`
- `new_ocr_marker_chain_classifier_allowed`: `False`
- `filename_specific_parser_rules_allowed`: `False`
- `member_specific_rules_allowed`: `False`
- `hardcoded_receipt_ids_allowed`: `False`
- `selection_method`: `existing app receipt parser/store-detection output from parse_receipt_content`
- `resource_safety`: `R9-28B5/R9-28B6 diagnostics are executed only for selected AH receipts.`

## Batchsamenvatting

- `image_member_count`: `11`
- `ah_member_count_detected_by_existing_parser`: `0`
- `expected_ah_count`: `4`
- `selection_pass`: `False`
- `diagnostics_executed_for_selected_ah_count`: `0`
- `passed_count`: `0`
- `failed_or_suspicious_count`: `0`
- `failure_types`: `{'existing_parser_ah_selection_count_mismatch': 1}`
- `total_reconstructed_articles`: `0`

## Bestaande winkelherkenning per image-member

| Member | Geselecteerd als AH | Store/chain uit bestaande parser | Parse ok | Call style | Diagnostics uitgevoerd | Artikelen | Som | Suspicious |
|---|---:|---|---:|---|---:|---:|---:|---:|
| `AH foto 2.jpeg` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `AH foto 3.jpg` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `Aldi foto 1.jpg` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `Aldi foto 2.jpg` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `Jumbo App 1.png` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `Jumbo foto 1.jpeg` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `Jumbo foto 3.jpg` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `Lidl App 1.png` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `Lidl App 2.png` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `Plus foto 2.jpeg` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |
| `plus foto 1.jpg` | `False` | `None` | `False` | `None` | `False` | `0` | `0` | `0` |

## Gereconstrueerde AH-artikelen per geselecteerde AH-bon met diagnostics
