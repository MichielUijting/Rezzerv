# Verwijderrapport batch 9

## Doel

Verwijderen van verouderde cleanup-tools die uitsluitend bedoeld waren voor eerdere opschoonrondes.

## Vooraf gecontroleerd

De cleanup-tools hebben geen externe runtimeverwijzingen. De gevonden verwijzingen zijn alleen zelfverwijzingen of onderlinge verwijzingen binnen dezelfde cleanup-tooling.

## Verwijderd

- tools/cleanup_legacy_patch_tools.py
- tools/cleanup_reports_tmp.py
- tools/cleanup_root_debug_scripts.py

## Bewust behouden

- tools/R9-SYNC-REVIEW-CLEANUP_DECISION_20260525.md

## Reden

Het besluitdocument blijft als historisch consolidatiebewijs behouden. De cleanup-tools zelf zijn achterhaald, omdat de bijbehorende debug-output, patcharchieven en generated inventory inmiddels zijn verwijderd.
