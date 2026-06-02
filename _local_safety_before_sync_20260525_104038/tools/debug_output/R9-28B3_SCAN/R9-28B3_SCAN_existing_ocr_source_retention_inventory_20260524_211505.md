# R9-28B3-SCAN — Existing OCR/source retention inventory

Gemaakt: `2026-05-24T21:15:05`

## Scope

- inventory only
- no parser change
- no OCR change
- no database mutation
- no status determination
- no UI change
- no receipt_status_baseline_service_v4.py modification

## SSOT-compliance

- `status_determination`: `not_performed`
- `status_service`: `receipt_status_baseline_service_v4.py`
- `parse_status_used_as_truth`: `False`
- `parser_mutated`: `False`
- `database_mutated`: `False`
- `baseline_mutated`: `False`
- `ui_touched`: `False`

## Conclusie

**Besluit:** Niet bouwen aan nieuwe raw OCR-retentie totdat exact is vastgesteld of bestaande OCR/diagnostics-code pre-parser OCR-regels of bounding boxes al beschikbaar maakt.

### Bestaande functionaliteit
- OCR-runtime code is aanwezig: zoekresultaten bevatten Paddle/Tesseract/OCR-routes en OCR-helperfuncties.
- Diagnostieklaag is aanwezig: processing_diagnostics, parser diagnosis, explainability en normalized review diagnostics komen voor.
- Persistente receipt-tabellen zijn aanwezig: raw_receipts, receipt_tables, receipt_table_lines, receipt_processing_runs en importtabellen komen voor.
- Er zijn raw/text/line velden en variabelen aanwezig, maar per codepad moet worden vastgesteld of dit pre-parser OCR is of post-parser output.

### Ontbrekend of onzeker

### Hergebruikstrategie
- Gebruik bestaande diagnosemodules/routes als voorkeursingang voor AH-ketenanalyse.
- Onderzoek testing_receipt_parser_diagnosis_routes.py eerst; dit is waarschijnlijk de bestaande diagnose-ingang voor parser/OCR review.
- Onderzoek receipt_service.py als huidige orchestrator: OCR, parsing, raw_receipts en receipt_table_lines lijken daar bij elkaar te komen.

### Risico's en guardrails
- Statusgerelateerde code is aanwezig in scanresultaten. R9-28B3-SCAN mag dit alleen inventariseren; geen wijziging in statusservice of parse_status-gebruik.

## Match-samenvatting

```json
{
  "diagnostics": 431,
  "status_risk": 1172,
  "persistence_tables": 510,
  "bounding_boxes_or_layout": 1238,
  "raw_text_or_lines": 701,
  "ocr_runtime": 119
}
```

## Belangrijkste bestanden

- `tools/debug_output/R9-28A4_reports/R9-28A4_ah_semantic_line_classification_audit_ssot_clean_20260524_183517.json` — matches: `459` — categories: `{'status_risk': 3, 'persistence_tables': 7, 'raw_text_or_lines': 1, 'bounding_boxes_or_layout': 448}`
- `tools/debug_output/R9-28B_reports/R9-28B_ah_chain_section_classifier_ssot_safe_20260524_185430.json` — matches: `459` — categories: `{'status_risk': 2, 'persistence_tables': 6, 'raw_text_or_lines': 1, 'bounding_boxes_or_layout': 450}`
- `tools/reports/R9-23B_receipt_line_diagnosis.json` — matches: `459` — categories: `{'status_risk': 15, 'raw_text_or_lines': 444}`
- `backend/app/main.py` — matches: `379` — categories: `{'persistence_tables': 234, 'raw_text_or_lines': 40, 'diagnostics': 22, 'status_risk': 58, 'bounding_boxes_or_layout': 25}`
- `reports/receipt_analysis/r7c35c_receipt_status_details_dump.json` — matches: `235` — categories: `{'status_risk': 235}`
- `backend/app/services/receipt_service.py` — matches: `130` — categories: `{'ocr_runtime': 21, 'status_risk': 32, 'raw_text_or_lines': 29, 'bounding_boxes_or_layout': 16, 'persistence_tables': 32}`
- `backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py` — matches: `73` — categories: `{'diagnostics': 73}`
- `tmp/r7c16_ah3_geometry.json` — matches: `71` — categories: `{'bounding_boxes_or_layout': 36, 'raw_text_or_lines': 35}`
- `backend/app/domains/receipts/image/receipt_photo_normalizer.py` — matches: `67` — categories: `{'diagnostics': 60, 'bounding_boxes_or_layout': 7}`
- `tools/check_r7c16_ah3_perspective_geometry_diagnostics.py` — matches: `60` — categories: `{'ocr_runtime': 4, 'bounding_boxes_or_layout': 47, 'raw_text_or_lines': 7, 'diagnostics': 2}`
- `backend/app/testing/receipt_status_baseline/expected_status_v4.json` — matches: `48` — categories: `{'status_risk': 48}`
- `backend/app/testing/receipt_status_baseline/expected_status_v5.json` — matches: `48` — categories: `{'status_risk': 48}`
- `backend/app/testing/receipt_status_baseline/expected_status_v6.json` — matches: `48` — categories: `{'status_risk': 48}`
- `backend/app/services/receipt_status_baseline_service.py` — matches: `40` — categories: `{'status_risk': 16, 'raw_text_or_lines': 11, 'persistence_tables': 9, 'bounding_boxes_or_layout': 4}`
- `tools/check_r7c12_ah3_topology_reconstruction_diagnostics.py` — matches: `36` — categories: `{'ocr_runtime': 4, 'bounding_boxes_or_layout': 30, 'diagnostics': 2}`
- `reports/receipt_validation/r7c33_receipt_validation_report.json` — matches: `35` — categories: `{'persistence_tables': 18, 'status_risk': 17}`
- `tools/debug_output/R9-28B2_reports/R9-28B2_ah_raw_source_section_classifier_ssot_safe_20260524_185912.json` — matches: `34` — categories: `{'status_risk': 2, 'persistence_tables': 22, 'diagnostics': 1, 'raw_text_or_lines': 3, 'bounding_boxes_or_layout': 6}`
- `backend/app/testing_receipt_parser_diagnosis_routes.py` — matches: `32` — categories: `{'status_risk': 13, 'raw_text_or_lines': 8, 'bounding_boxes_or_layout': 3, 'persistence_tables': 7, 'diagnostics': 1}`
- `backend/app/services/receipt_status_baseline_service_v4.py` — matches: `28` — categories: `{'status_risk': 18, 'persistence_tables': 10}`
- `backend/receipt_ingestion/normalized_review_diagnostics.py` — matches: `28` — categories: `{'diagnostics': 28}`
- `tools/reports/R9-10_receipt_ssot_scorematrix_20260523_115054.json` — matches: `28` — categories: `{'status_risk': 28}`
- `tools/reports/R9-10_receipt_ssot_scorematrix_20260523_170917.json` — matches: `28` — categories: `{'status_risk': 28}`
- `tools/reports/R9-10_receipt_ssot_scorematrix_20260524_172950.json` — matches: `28` — categories: `{'status_risk': 28}`
- `tools/reports/R9-10_receipt_ssot_scorematrix_20260524_175602.json` — matches: `28` — categories: `{'status_risk': 28}`
- `backend/app/receipt_recompute_policy_patch.py` — matches: `27` — categories: `{'bounding_boxes_or_layout': 3, 'persistence_tables': 10, 'raw_text_or_lines': 6, 'status_risk': 8}`
- `tools/R9-28B3_SCAN_existing_ocr_source_retention_inventory.py` — matches: `26` — categories: `{'status_risk': 4, 'diagnostics': 8, 'ocr_runtime': 3, 'persistence_tables': 10, 'bounding_boxes_or_layout': 1}`
- `backend/app/testing/receipt_status_baseline/expected_status_v3.json` — matches: `24` — categories: `{'status_risk': 24}`
- `backend/app/testing/receipt_status_baseline/baseline_receipts_v3.json` — matches: `23` — categories: `{'status_risk': 23}`
- `backend/app/testing/receipt_status_baseline/expected_status_v2.json` — matches: `23` — categories: `{'status_risk': 23}`
- `backend/receipt_ingestion/kassa_active_scope_kpi.py` — matches: `23` — categories: `{'status_risk': 18, 'persistence_tables': 5}`

## OCR-/diagnosefuncties

- `backend/app/api/dev_system_routes.py:16` — `get_dev_status` — `status_related_do_not_touch`
- `backend/app/api/receipt_admin_routes.py:73` — `run_receipt_status_backfill` — `status_related_do_not_touch`
- `backend/app/api/receipt_admin_routes.py:81` — `run_receipt_status_baseline_validation` — `receipt_parser_or_retention`
- `backend/app/api/receipt_admin_routes.py:89` — `run_receipt_status_baseline_diagnosis` — `diagnostics`
- `backend/app/api/receipt_diagnosis_routes.py:19` — `receipt_line_diagnosis` — `diagnostics`
- `backend/app/api/receipt_diagnosis_routes.py:29` — `receipt_line_diagnosis_download` — `diagnostics`
- `backend/app/api/receipt_diagnosis_routes.py:47` — `receipt_parser_diagnosis` — `diagnostics`
- `backend/app/api/receipt_diagnosis_routes.py:53` — `receipt_parser_diagnosis_download` — `diagnostics`
- `backend/app/api/receipt_diagnostics_routes.py:34` — `get_receipt_diagnostics_route_inventory` — `diagnostics`
- `backend/app/api/receipt_diagnostics_routes.py:40` — `get_receipt_line_quality` — `receipt_parser_or_retention`
- `backend/app/api/receipt_diagnostics_routes.py:45` — `download_receipt_line_quality` — `receipt_parser_or_retention`
- `backend/app/api/receipt_diagnostics_routes.py:63` — `get_receipt_parser_quality` — `receipt_parser_or_retention`
- `backend/app/api/receipt_diagnostics_routes.py:68` — `download_receipt_parser_quality` — `receipt_parser_or_retention`
- `backend/app/api/receipt_diagnostics_routes.py:80` — `get_receipt_diagnostics_kpi` — `diagnostics`
- `backend/app/api/receipt_diagnostics_routes.py:86` — `get_receipt_diagnostics_kpi_scope` — `diagnostics`
- `backend/app/api/receipt_import_diagnosis_routes.py:22` — `get_receipt_import_diagnosis_health` — `diagnostics`
- `backend/app/api/receipt_import_diagnosis_routes.py:31` — `diagnose_receipt_zip_import` — `diagnostics`
- `backend/app/api/receipt_import_diagnosis_routes.py:94` — `_diagnose_single_file` — `diagnostics`
- `backend/app/api/receipt_ingestion_review_routes.py:52` — `configure_receipt_ingestion_review_routes` — `diagnostics`
- `backend/app/api/receipt_ingestion_review_routes.py:333` — `get_receipt_ingestion_review_readiness_baseline` — `diagnostics`
- `backend/app/api/receipt_ingestion_review_routes.py:354` — `get_receipt_ingestion_review_preview` — `diagnostics`
- `backend/app/api/receipt_ingestion_review_routes.py:373` — `get_receipt_ingestion_explainability_preview` — `diagnostics`
- `backend/app/api/receipt_kpi_routes.py:16` — `get_receipt_kpi_baseline` — `receipt_parser_or_retention`
- `backend/app/api/receipt_kpi_routes.py:27` — `get_receipt_kpi_scope_diagnosis` — `diagnostics`
- `backend/app/api/receipt_po_status_delta_routes.py:20` — `build_po_status_delta_report` — `status_related_do_not_touch`
- `backend/app/api/receipt_po_status_delta_routes.py:76` — `receipt_po_status_delta` — `status_related_do_not_touch`
- `backend/app/api/receipt_po_status_delta_routes.py:81` — `receipt_po_status_delta_download` — `status_related_do_not_touch`
- `backend/app/api/receipt_preview_routes.py:23` — `configure_receipt_preview_routes` — `diagnostics`
- `backend/app/api/receipt_preview_routes.py:48` — `_generate_fallback_processed_preview` — `diagnostics`
- `backend/app/api/receipt_preview_routes.py:66` — `get_receipt_preview` — `diagnostics`
- `backend/app/api/routes/receipt_db_snapshot.py:35` — `_count_by_status` — `status_related_do_not_touch`
- `backend/app/api/routes/receipt_parser_diagnosis.py:92` — `build_receipt_parser_diagnosis` — `diagnostics`
- `backend/app/api/routes/receipt_parser_diagnosis.py:231` — `get_receipt_parser_diagnosis` — `diagnostics`
- `backend/app/api/routes/receipt_parser_diagnosis.py:239` — `download_receipt_parser_diagnosis` — `diagnostics`
- `backend/app/domains/receipts/image/receipt_photo_normalizer.py:416` — `_make_ocr_ready` — `ocr_runtime`
- `backend/app/domains/receipts/receipt_service.py:17` — `parse_receipt_content` — `receipt_parser_or_retention`
- `backend/app/main.py:483` — `normalize_status` — `status_related_do_not_touch`
- `backend/app/main.py:541` — `validate_review_decision` — `diagnostics`
- `backend/app/main.py:1490` — `normalize_global_product_status` — `status_related_do_not_touch`
- `backend/app/main.py:3208` — `get_article_enrichment_status` — `status_related_do_not_touch`
- `backend/app/main.py:4797` — `find_global_product_match_for_receipt_line` — `receipt_parser_or_retention`
- `backend/app/main.py:4899` — `resolve_receipt_line_product_links` — `receipt_parser_or_retention`
- `backend/app/main.py:5086` — `sync_receipt_table_line_product_links` — `receipt_parser_or_retention`
- `backend/app/main.py:6868` — `_receipt_line_display_clause` — `receipt_parser_or_retention`
- `backend/app/main.py:6872` — `_receipt_line_quantity_clause` — `receipt_parser_or_retention`
- `backend/app/main.py:6876` — `_receipt_line_unit_clause` — `receipt_parser_or_retention`
- `backend/app/main.py:6880` — `_receipt_line_unit_price_clause` — `receipt_parser_or_retention`
- `backend/app/main.py:6884` — `_receipt_line_total_clause` — `receipt_parser_or_retention`
- `backend/app/main.py:6888` — `_receipt_line_active_filter` — `receipt_parser_or_retention`
- `backend/app/main.py:7094` — `get_store_review_article_options` — `diagnostics`
- `backend/app/main.py:7216` — `resolve_review_article_option` — `diagnostics`
- `backend/app/main.py:7944` — `compute_batch_status` — `status_related_do_not_touch`
- `backend/app/main.py:7978` — `update_batch_status` — `status_related_do_not_touch`
- `backend/app/main.py:8734` — `recompute_receipt_review_state` — `diagnostics`
- `backend/app/main.py:8801` — `derive_unpack_receipt_status` — `status_related_do_not_touch`
- `backend/app/main.py:8808` — `map_parse_status_to_ui` — `status_related_do_not_touch`
- `backend/app/main.py:8865` — `sync_unpack_batch_lines_for_receipt` — `receipt_parser_or_retention`
- `backend/app/main.py:9963` — `build_receipt_inbound_status` — `status_related_do_not_touch`
- `backend/app/main.py:10079` — `parse_email_receipt_payload` — `receipt_parser_or_retention`
- `backend/app/main.py:10683` — `backfill_receipt_unpack_statuses` — `status_related_do_not_touch`
- `backend/app/main.py:10817` — `run_receipt_status_backfill` — `status_related_do_not_touch`
- `backend/app/main.py:10824` — `run_receipt_status_baseline_validation` — `receipt_parser_or_retention`
- `backend/app/main.py:10831` — `run_receipt_status_baseline_diagnosis` — `diagnostics`
- `backend/app/main.py:10990` — `get_receipt_import_batch_status` — `status_related_do_not_touch`
- `backend/app/main.py:11163` — `get_receipt_gmail_status` — `status_related_do_not_touch`
- `backend/app/main.py:11629` — `get_receipt_explainability` — `diagnostics`
- `backend/app/main.py:11818` — `update_receipt_line` — `receipt_parser_or_retention`
- `backend/app/main.py:11876` — `create_receipt_line` — `receipt_parser_or_retention`
- `backend/app/main.py:12020` — `reparse_receipt_table` — `receipt_parser_or_retention`
- `backend/app/main.py:12030` — `reparse_suspicious_receipts` — `receipt_parser_or_retention`
- `backend/app/main.py:13303` — `get_dev_status` — `status_related_do_not_touch`
- `backend/app/main.py:13452` — `run_store_location_diagnostic` — `diagnostics`
- `backend/app/main.py:13514` — `run_store_process_validation_diagnostic` — `diagnostics`
- `backend/app/main.py:14418` — `inventory_preview` — `diagnostics`
- `backend/app/main.py:15455` — `get_store_review_articles` — `diagnostics`
- `backend/app/main.py:15815` — `review_purchase_import_line` — `diagnostics`
- `backend/app/main.py:16016` — `complete_purchase_import_batch_review` — `diagnostics`
- `backend/app/main.py:16066` — `build_purchase_import_line_diagnostic` — `diagnostics`
- `backend/app/main.py:16139` — `store_purchase_import_line_diagnostic` — `diagnostics`
- `backend/app/main.py:16148` — `build_purchase_import_batch_diagnostics` — `diagnostics`

## Database-inspectie

- DB: `.\backend\data\rezzerv.db`
- Exists: `True`
- `raw_receipts`: exists=`True`, rows=`232`, text_like_columns=`['duplicate_of_raw_receipt_id', 'raw_status']`
- `receipt_tables`: exists=`True`, rows=`232`, text_like_columns=`['raw_receipt_id']`
- `receipt_table_lines`: exists=`True`, rows=`1748`, text_like_columns=`['raw_label', 'normalized_label', 'corrected_raw_label']`
- `receipt_processing_runs`: exists=`True`, rows=`0`, text_like_columns=`[]`
- `purchase_import_batches`: exists=`True`, rows=`17`, text_like_columns=`['raw_payload']`
- `purchase_import_lines`: exists=`True`, rows=`117`, text_like_columns=`['article_name_raw', 'brand_raw', 'quantity_raw', 'unit_raw', 'line_price_raw', 'processing_diagnostics']`
- `receipt_import_batches`: exists=`True`, rows=`16`, text_like_columns=`['latest_raw_receipt_id', 'results_json']`
- `receipt_email_messages`: exists=`True`, rows=`0`, text_like_columns=`['raw_receipt_id', 'body_text', 'body_html']`

## Volgende stap

R9-28B4 mag pas worden gekozen na review van dit scanrapport.
