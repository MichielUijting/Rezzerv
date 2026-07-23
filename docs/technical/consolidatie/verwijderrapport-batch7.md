# Verwijderrapport batch 7

## Doel

Verwijderen van oude documentatie- en debugdiagnostiek die geen actuele runtimefunctie heeft en alleen nog als historische ballast voorkomt.

## Behouden

De volgende backenddiagnostiek is bewust behouden omdat deze actief wordt geïmporteerd of gebruikt:

- backend/receipt_ingestion/diagnostics/__init__.py
- backend/receipt_ingestion/diagnostics/summary.py
- backend/receipt_ingestion/normalized_review_diagnostics.py

## Verwijderd

- R7c diagnosedocumenten onder docs/architecture
- oude diagnosefile docs/Rezzerv-v01.08.98-diagnose-op-v01.08.96-basis.txt
- oude debug-outputmap tools/debug_output/R9-28B3_SCAN

## Reden

De verwijderde bestanden zijn historische diagnose- en scanoutput. Ze zijn geen actuele SSOT, geen runtimecode en geen vereiste regressiebron.
