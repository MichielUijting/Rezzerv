# R7c-4 — SSOT-compliant supermarket regression runner

Status: supermarket regression infrastructure  
Branch: `sync/local-rezzerv-receipt-basis-v2`

## Doel

R7c-4 introduceert de eerste SSOT-compliant supermarket parser regression runner.

De runner vergelijkt supermarkt-parseruitkomsten met baseline V6 zonder eigen statuslogica te introduceren.

Belangrijk uitgangspunt:

```text
receipt_status_baseline_service_v4.py
```

blijft de enige bron van waarheid voor kassabonstatus.

## SSOT-regels

R7c-4 volgt expliciet de SSOT-regels:

- parser levert alleen data;
- parserstatus is diagnostisch;
- categorisering gebeurt uitsluitend via `po_norm_status_label`;
- backendstatus moet gelijk zijn aan PO-status;
- `verschil` moet 0 zijn.

De runner gebruikt daarom:

- `po_norm_status_label`
- `backend_status_counts`
- `po_norm_status_counts`
- `verschil`

uit de baseline service payload.

## Belangrijke architectuurregel

De runner mag:

```text
technical_parse_status
```

wel tonen voor diagnose,

maar NOOIT gebruiken voor:

- categorisering;
- telling;
- pass/fail;
- UI-waarheid.

## Scope

Alleen supermarktfixtures.

Niet in scope:

- Action;
- Gamma;
- Hornbach;
- Bol;
- MediaMarkt;
- Karwei;
- parserfixes;
- OCR-tuning.

## Input

### Canonical fixture registry

Input uit:

```text
r7c3_canonical_registry.csv
```

### SSOT baseline payload

De runner ondersteunt:

- live backend endpoint;
- of een eerder geëxporteerde JSON payload.

## Tooling

Toegevoegd:

```text
tools/check_r7c4_ssot_supermarket_regression_runner.py
```

Eigenschappen:

- standalone;
- geen SQLAlchemy imports;
- geen parserstatuslogica;
- deterministic output;
- SSOT-validatie ingebouwd.

## Ondersteunde modi

### Mode 1 — live backend

```powershell
python tools/check_r7c4_ssot_supermarket_regression_runner.py `
  --registry ".\tmp\r7c3_canonical_registry.csv" `
  --backend-url "http://localhost:8011"
```

### Mode 2 — offline JSON

```powershell
python tools/check_r7c4_ssot_supermarket_regression_runner.py `
  --registry ".\tmp\r7c3_canonical_registry.csv" `
  --status-json ".\tmp\receipt_status_payload.json"
```

## SSOT-validaties

De runner controleert:

```text
backend_status_counts == po_norm_status_counts
verschil == 0
```

Indien niet:

```text
BUG
```

## Per-fixture output

Per supermarktfixture:

- canonical_fixture_id;
- fixture_file;
- baseline_receipt_id;
- expected_total;
- actual_total;
- expected_line_count;
- actual_line_count;
- po_norm_status_label;
- technical_parse_status;
- result;
- failed_criteria.

## Outputbestanden

Optioneel:

```text
tmp/r7c4_regression_results.json
tmp/r7c4_regression_summary.csv
```

## Strategisch belang

R7c-4 is de eerste stap waarin supermarktparsergedrag systematisch en reproduceerbaar wordt gemeten tegen baseline V6.

Nog zonder parserwijzigingen.

Nog zonder OCR-optimalisatie.

Wel met:

- deterministic fixtures;
- canonical IDs;
- SSOT-statuscontrole;
- reproduceerbare regressie-output.

## Verwachte vervolgstap

```text
R7c-5 — deterministic supermarket regression snapshots
```

Doel:

- stabiele regression snapshots opslaan;
- fixturehistorie volgen;
- parserdelta's reproduceerbaar maken;
- toekomstige parserverbeteringen veilig testen.
