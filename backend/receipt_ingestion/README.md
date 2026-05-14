# Receipt Ingestion Engine (Phase 1)

## Doel

Consolidatie van de bestaande `tools/receipt_csv_poc` naar een onderhoudbare, modulaire Receipt Ingestion Engine.

Deze fase:
- verandert GEEN parseroutput;
- verandert GEEN UI;
- verandert GEEN database;
- promoot GEEN shadow rows naar echte parser rows.

De engine werkt voorlopig als orchestrator/wrapper rond bestaande POC-functionaliteit.

---

# Structuur

```text
backend/receipt_ingestion/
├── __init__.py
├── contracts.py
├── pipeline.py
├── preprocessing/
├── ocr/
├── parsing/
├── diagnostics/
├── safety/
└── evaluation/
```

---

# Centrale outputstructuur

```json
{
  "receipt_id": "...",
  "source_file": "...",
  "parser_rows": [],
  "review_suggestions": [],
  "diagnostics": {},
  "quality_status": "controlled | review_needed | failed",
  "engine_version": "receipt-ingestion-v01"
}
```

---

# CLI gebruik

## Eén bon verwerken

```bash
python -m backend.receipt_ingestion.pipeline \
  --json test_runs/run_x/json/AH\ foto\ 2.json \
  --output out.json
```

## Hele map verwerken

```bash
python -m backend.receipt_ingestion.pipeline \
  --json-dir test_runs/run_x/json \
  --output out.json
```

---

# Wat gebeurt er nu technisch?

De orchestrator:
- leest bestaande POC-json-output;
- bouwt parser_rows;
- verzamelt diagnostiek;
- maakt review_suggestions;
- bepaalt quality_status.

Nog NIET:
- echte adaptive preprocessing execution;
- parser replacement;
- database persistence;
- UI integration.

---

# Bestaande Q1-Q14 diagnostics

De volgende diagnostics blijven beschikbaar via wrappers:

- quantity_merge_amount_diagnostics
- discount_netto_diagnostics
- ocr_structural_normalization
- document_isolation_enhancement_diagnostics
- adaptive_ocr_orchestration
- cross_route_ocr_consensus
- consensus_weighted_shadow_reconstruction
- simulated_parser_integration
- parser_safety_gating
- pre_ocr_image_correction_governance
- adaptive_preprocessing_simulation
- zone_aware_preprocessing_diagnostics
- cross_zone_interference_diagnostics
- preprocessing_sequence_diagnostics

---

# Wat moet later vervangen worden?

De huidige fase gebruikt nog wrappers rond losse scripts.

Later moeten worden gemigreerd naar nette modules:

- preprocessing orchestration
- OCR execution
- parser execution
- diagnostics generation
- safety gating
- evaluation pipeline

---

# Belangrijke architectuurregel

Shadow/simulated rows mogen NIET automatisch parser_rows worden.

Alleen review_suggestions zijn voorlopig toegestaan.
