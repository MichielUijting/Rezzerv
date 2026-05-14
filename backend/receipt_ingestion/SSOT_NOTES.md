# SSOT compliance notes

## BELANGRIJKE REGEL

De Receipt Ingestion Engine bepaalt NOOIT de kassabonstatus of categorie.

De ENIGE toegestane bron voor kassabonstatus is:

```text
receipt_status_baseline_service_v4.py
```

## Verboden in de ingestion engine

- quality_status
- controlled/review_needed categorieën
- parse_status als categoriebron
- frontend fallback statuslogica
- backend categorisering buiten de baseline service

## Toegestaan

De engine mag uitsluitend:

- parser_rows leveren
- diagnostics leveren
- review_suggestions leveren
- een TECHNISCHE engine_processing_state leveren

## engine_processing_state

Dit veld is UITSLUITEND technisch.

Toegestane waarden:

- parsed
- diagnostics_available
- failed

Dit veld mag NOOIT gebruikt worden voor:

- UI statusweergave
- backend tellingen
- categorie-indeling
- PO status

## po_norm_status_label

Dit veld mag alleen worden DOORGEGEVEN vanuit upstream statusservices.

De ingestion engine:

- berekent dit veld NIET
- interpreteert dit veld NIET
- gebruikt dit veld NIET voor beslissingen

## UI/API regel

UI en API mogen uitsluitend:

```text
po_norm_status_label
```

gebruiken voor kassaboncategorieën.
