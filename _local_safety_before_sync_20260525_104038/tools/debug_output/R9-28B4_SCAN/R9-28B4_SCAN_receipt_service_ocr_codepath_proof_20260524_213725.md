# R9-28B4-SCAN — Receipt service OCR codepath proof

Gemaakt: `2026-05-24T21:37:25`

## SSOT-compliance

- `status_determination`: `not_performed`
- `parse_status_used_as_truth`: `False`
- `parser_mutated`: `False`
- `ocr_mutated`: `False`
- `database_mutated`: `False`
- `baseline_mutated`: `False`
- `ui_touched`: `False`

## Bewijsantwoorden

- `raw_ocr_exists_in_memory`: `True`
- `bounding_boxes_exist_in_memory`: `True`
- `grouped_ocr_lines_exist_before_parser`: `True`
- `post_parser_lines_are_persisted`: `True`
- `raw_receipt_file_metadata_is_persisted`: `True`
- `pre_parser_ocr_lines_or_boxes_persisted`: `False`
- `existing_diagnosis_routes_present`: `True`
- `recommended_next_step`: `R9-28B5 — expose existing in-memory pre-parser OCR lines and Paddle boxes via SSOT-safe diagnostics/export; do not add parser/status logic.`

## Bestanden en functieblokken

### `backend/app/services/receipt_service.py`
- exists: `True`
- category_counts: `{'persist_receipt_tables': 99, 'paddle_raw_texts': 19, 'status_guardrail': 29, 'line_grouping': 23, 'persist_raw_receipts': 20, 'persist_receipt_table_lines': 46, 'tesseract_lines': 25, 'paddle_boxes': 11, 'parse_input': 19}`
  - `_ocr_bbox_to_line_anchor` regels `1469-1487` counts `{'paddle_boxes': 1}`
  - `_extract_payload_from_paddle_item` regels `1490-1512` counts `{}`
  - `_group_paddle_texts_to_lines` regels `1515-1559` counts `{'paddle_raw_texts': 6, 'paddle_boxes': 1, 'line_grouping': 2}`
  - `_normalize_paddle_collection` regels `1562-1575` counts `{}`
  - `_ocr_image_text_with_paddle` regels `1579-1618` counts `{'paddle_raw_texts': 8, 'paddle_boxes': 7, 'line_grouping': 1}`
  - `_ocr_image_text_with_tesseract` regels `1622-1638` counts `{'tesseract_lines': 7}`
  - `parse_receipt_content` regels `2344-2478` counts `{'parse_input': 12, 'tesseract_lines': 13, 'status_guardrail': 2, 'persist_receipt_tables': 3}`
  - `reparse_receipt` regels `2745-2868` counts `{'persist_raw_receipts': 4, 'persist_receipt_tables': 10, 'parse_input': 1, 'persist_receipt_table_lines': 5, 'status_guardrail': 4, 'line_grouping': 3}`

### `backend/app/api/routes/receipt_parser_diagnosis.py`
- exists: `True`
- category_counts: `{'status_guardrail': 7, 'persist_receipt_table_lines': 6, 'persist_receipt_tables': 11, 'diagnosis_routes': 6, 'persist_raw_receipts': 1, 'parse_input': 1}`
  - `_difference` regels `75-81` counts `{'persist_receipt_tables': 3}`
  - `build_receipt_parser_diagnosis` regels `92-227` counts `{'diagnosis_routes': 1, 'persist_receipt_tables': 8, 'status_guardrail': 4, 'persist_raw_receipts': 1, 'persist_receipt_table_lines': 5, 'parse_input': 1}`
  - `get_receipt_parser_diagnosis` regels `231-235` counts `{'diagnosis_routes': 2}`
  - `download_receipt_parser_diagnosis` regels `239-245` counts `{'diagnosis_routes': 3}`

### `backend/app/testing_receipt_parser_diagnosis_routes.py`
- exists: `True`
- category_counts: `{'parse_input': 3, 'status_guardrail': 13, 'persist_receipt_table_lines': 15, 'persist_receipt_tables': 13, 'line_grouping': 3, 'persist_raw_receipts': 7, 'diagnosis_routes': 8}`
  - `_status_label` regels `15-21` counts `{'status_guardrail': 4}`
  - `_parse_result_to_dict` regels `36-62` counts `{'persist_receipt_table_lines': 3, 'status_guardrail': 1, 'persist_receipt_tables': 1}`
  - `_receipt_line_dict` regels `65-87` counts `{'persist_receipt_table_lines': 5, 'line_grouping': 1}`
  - `_build_reparse_from_source` regels `90-104` counts `{'persist_raw_receipts': 5, 'parse_input': 1}`
  - `build_receipt_parser_diagnosis` regels `107-284` counts `{'diagnosis_routes': 1, 'persist_raw_receipts': 2, 'persist_receipt_tables': 12, 'status_guardrail': 8, 'line_grouping': 2, 'persist_receipt_table_lines': 7, 'parse_input': 1}`
  - `install_receipt_parser_diagnosis_routes` regels `291-309` counts `{'diagnosis_routes': 7}`
  - `receipt_parser_diagnosis` regels `297-298` counts `{'diagnosis_routes': 2}`
  - `receipt_parser_diagnosis_download` regels `301-309` counts `{'diagnosis_routes': 3}`

### `backend/app/testing_receipt_line_diagnosis_routes.py`
- exists: `True`
- category_counts: `{'parse_input': 3, 'status_guardrail': 2, 'persist_receipt_table_lines': 16, 'line_grouping': 3, 'persist_raw_receipts': 7, 'persist_receipt_tables': 8, 'diagnosis_routes': 8}`
  - `_receipt_line_dict` regels `32-50` counts `{'persist_receipt_table_lines': 5, 'line_grouping': 1}`
  - `_build_producer_trace` regels `83-113` counts `{'persist_receipt_table_lines': 3, 'parse_input': 1}`
  - `_reparse_line_dict` regels `116-132` counts `{'persist_receipt_table_lines': 3}`
  - `_build_live_reparse` regels `135-160` counts `{'persist_raw_receipts': 5, 'parse_input': 1, 'persist_receipt_tables': 2}`
  - `build_receipt_line_diagnosis` regels `176-255` counts `{'diagnosis_routes': 1, 'persist_receipt_table_lines': 5, 'persist_raw_receipts': 2, 'persist_receipt_tables': 6, 'line_grouping': 2, 'status_guardrail': 1}`
  - `install_receipt_line_diagnosis_routes` regels `265-289` counts `{'diagnosis_routes': 7}`
  - `receipt_line_diagnosis` regels `271-272` counts `{'diagnosis_routes': 2}`
  - `receipt_line_diagnosis_download` regels `275-289` counts `{'diagnosis_routes': 3}`

### `backend/app/receipt_ingestion/text_layout_regions.py`
- exists: `True`
- category_counts: `{'persist_receipt_tables': 8, 'paddle_raw_texts': 2, 'paddle_boxes': 10}`
  - `box_from_ocr_bbox` regels `62-93` counts `{'paddle_boxes': 1}`
  - `cluster_text_regions` regels `96-158` counts `{'paddle_boxes': 7, 'persist_receipt_tables': 4, 'paddle_raw_texts': 1}`
  - `select_primary_text_region` regels `161-204` counts `{'persist_receipt_tables': 3}`
  - `build_text_layout_diagnostic` regels `207-217` counts `{'paddle_boxes': 2}`

### `tools/check_r7c8_paddle_text_layout_diagnostics.py`
- exists: `True`
- category_counts: `{'paddle_boxes': 6, 'paddle_raw_texts': 8}`
  - `import_paddle_ocr` regels `56-61` counts `{'paddle_raw_texts': 3}`
  - `create_paddle_model` regels `104-117` counts `{'paddle_raw_texts': 3}`
  - `analyse_image` regels `120-138` counts `{'paddle_boxes': 5, 'paddle_raw_texts': 2}`

### `tools/check_r7c11d_ah_foto_3_route_diagnostics.py`
- exists: `True`
- category_counts: `{'paddle_raw_texts': 10, 'parse_input': 4, 'tesseract_lines': 11, 'paddle_boxes': 3, 'persist_receipt_tables': 9, 'status_guardrail': 1}`
  - `get_paddle` regels `44-58` counts `{'paddle_raw_texts': 4}`
  - `paddle_lines` regels `72-83` counts `{'parse_input': 1, 'paddle_raw_texts': 5, 'paddle_boxes': 3}`
  - `tesseract_lines` regels `86-91` counts `{'tesseract_lines': 4}`
  - `parse_lines` regels `94-104` counts `{'parse_input': 1, 'persist_receipt_tables': 3, 'status_guardrail': 1}`
  - `score` regels `107-118` counts `{'persist_receipt_tables': 2}`
  - `analyse` regels `121-133` counts `{'parse_input': 1, 'tesseract_lines': 6, 'persist_receipt_tables': 1}`
  - `main` regels `136-164` counts `{'persist_receipt_tables': 3}`

### `tools/check_r7c12_ah3_topology_reconstruction_diagnostics.py`
- exists: `True`
- category_counts: `{'paddle_raw_texts': 9, 'paddle_boxes': 29, 'line_grouping': 5, 'persist_receipt_tables': 3}`
  - `get_model` regels `52-62` counts `{'paddle_raw_texts': 2}`
  - `collect_boxes` regels `112-128` counts `{'paddle_raw_texts': 5, 'paddle_boxes': 1}`
  - `cluster_lines` regels `131-145` counts `{'paddle_boxes': 7}`
  - `detect_price_anchors` regels `152-158` counts `{'line_grouping': 3, 'paddle_boxes': 3}`
  - `candidate_pairs` regels `161-171` counts `{'paddle_boxes': 2}`
  - `detect_total` regels `174-181` counts `{'paddle_boxes': 1}`
  - `detect_store` regels `184-188` counts `{'paddle_boxes': 2}`
  - `detect_purchase_at` regels `191-197` counts `{'paddle_boxes': 2}`
  - `main` regels `200-242` counts `{'paddle_boxes': 11, 'line_grouping': 2, 'persist_receipt_tables': 3}`
