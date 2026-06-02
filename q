[33mcommit 2fab9d4b6a3e26d6f55ecf9be5127b551833d17a[m[33m ([m[1;36mHEAD[m[33m -> [m[1;32mfeature/r9-30a-restore-generic-rembg[m[33m)[m
Author: MichielUijting <169062718+MichielUijting@users.noreply.github.com>
Date:   Sat May 30 22:59:46 2026 +0200

    R9-38A2a fix Lidl PDF diagnostics import

[1mdiff --git a/backend/app/receipt_ingestion/service_parts/store_specific_parsers.py b/backend/app/receipt_ingestion/service_parts/store_specific_parsers.py[m
[1mindex f3b54ac..2d5a7fb 100644[m
[1m--- a/backend/app/receipt_ingestion/service_parts/store_specific_parsers.py[m
[1m+++ b/backend/app/receipt_ingestion/service_parts/store_specific_parsers.py[m
[36m@@ -11,10 +11,11 @@[m [mfrom app.receipt_ingestion.amounts import ([m
     amount_to_float as _amount_to_float,[m
     parse_decimal as _parse_decimal,[m
     price_from_split_parts as _price_from_split_parts,[m
 )[m
 from app.receipt_ingestion.structured_product_gateway import append_structured_product_candidate[m
[32m+[m[32mfrom app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics[m
 from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult[m
 from app.receipt_ingestion.service_parts.text_extraction import ([m
     _html_to_text,[m
     _normalize_store_specific_text,[m
     _normalize_text_lines,[m
[36m@@ -706,5 +707,6 @@[m [mdef _parse_store_specific_result(file_bytes: bytes, filename: str, mime_type: st[m
         for parser in (_parse_bol_email_result, _parse_picnic_email_result):[m
             result = parser(text, normalized_html, filename, header_date=header_date)[m
             if result is not None and (result.lines or result.total_amount or result.purchase_at or result.store_name):[m
                 return result[m
     return None[m
[41m+[m
