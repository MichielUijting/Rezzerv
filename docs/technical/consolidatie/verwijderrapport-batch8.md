# Verwijderrapport batch 8

## Doel

Verwijderen van historische debug-output en oude patcharchieven die geen actuele runtime-, regressie- of architectuurfunctie meer hebben.

## Vooraf gecontroleerd

- tools/debug_output wordt alleen nog genoemd vanuit oude debug-output, cleanup-tools of historische beslisdocumentatie.
- deprecated/regression/patches heeft geen actieve verwijzingen.
- patches/frontend heeft geen actieve verwijzingen.

## Bewust behouden

De volgende bestanden zijn niet verwijderd omdat zij runtime- of mogelijke runtimebetekenis hebben:

- backend/app/api/receipt_diagnostics_routes.py
- backend/app/api/receipt_preview_routes.py
- backend/app/receipt_ingestion/parser_diagnostics.py
- backend/receipt_ingestion/diagnostics/__init__.py
- backend/receipt_ingestion/diagnostics/summary.py
- backend/receipt_ingestion/normalized_review_diagnostics.py
- backend/app/receipt_recompute_policy_patch.py
- backend/app/services/receipt_debug_artifacts_patch.py
- frontend/src/features/kassa/components/ReceiptPreviewCard.jsx
- frontend/src/lib/barcodeScanner.js
- frontend/src/lib/useBarcodeScanner.js

## Verwijderd

- tools/debug_output/
- deprecated/regression/patches/
- patches/frontend/

## Conclusie

Batch 8 verwijdert alleen historische output en patcharchieven. Runtimecode en actieve diagnostiek blijven behouden.
