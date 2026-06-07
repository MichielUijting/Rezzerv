# Rezzerv — Refactor Roadmap

Status: v0.5

Deze roadmap ordent refactoring en dead-code-cleanup. Er wordt niets verwijderd zonder traceability en bewijs.

## Werkwijze

1. Inventariseren.
2. Classificeren.
3. Test-/Swagger-bewijs vastleggen.
4. Refactoren zonder functionele wijziging.
5. Dode code verwijderen in aparte cleanup-PR.

## Prioriteit 1 — SSOT/statuslaag opschonen

### RR-01 — `backend/app/services/receipt_ssot_status.py`

**Status:** DONE

**Probleem:** bevatte historische runtime fallbackstatuslogica die functionele status kon afleiden uit parserstatus, totalen en NO_BASELINE_MATCH.

**Uitgevoerd:**

- Oude runtime fallbackstatus verwijderd.
- `apply_po_norm_status` blijft mapper van statusbaseline-service naar UI/API-velden.
- Geen fallback vanuit `parse_status`.
- Geen `runtime_status_source = parser` voor functionele UI-status.

**Acceptatie:**

- Swagger `validate-receipt-status-baseline` blijft groen.
- Kassa toont status uit `po_norm_status_label`.
- `findstr /S /N /I /C:"_r9_38d6_runtime_status_override" backend\app` geeft geen productiehit.

### RR-02 — `backend/app/services/receipt_status_baseline_service_v4.py`

**Status:** DONE

**Probleem:** compatibility shim met verwarrende naam.

**Uitgevoerd:**

1. Imports naar `receipt_status_baseline_service_v4` gecontroleerd.
2. Geen verwijzingen gevonden.
3. Shim verwijderd.

**Acceptatie:** FastAPI start; baselinevalidatie blijft groen.

## Prioriteit 2 — Repo-scope opschonen

### RR-03 — `_local_safety_before_sync_*`

**Status:** DONE

**Probleem:** lokale safety-archives stonden in Git en vervuilden de actieve Python-inventaris.

**Uitgevoerd:**

- `_local_safety_before_sync_20260525_104038` verwijderd uit Git.
- Python-inventaris opnieuw gegenereerd.
- Totaal aantal Python-bestanden is gedaald van 433 naar 365.
- `local_safety_archive` is verdwenen uit de inventariscategorieën.

**Acceptatie:**

- `local_safety_archive` is 0 of afwezig in de inventaris.
- `active_backend_app` blijft functioneel ongewijzigd.
- Geen wijziging in frontend, baseline V10 of productie-parserlogica.
- Swagger baselinevalidatie blijft groen.

### RR-04 — Root debug scripts

**Status:** DONE

**Probleem:** losse root scripts zoals `dump_*`, `peek_*`, `inspect_*`, `map_*` en `receipt_duplicates.py` vervuilden de repository.

**Uitgevoerd:**

- 15 root-debug-scripts verwijderd.
- Python-inventaris opnieuw gegenereerd.
- `root_debug_scripts` is verdwenen uit de inventariscategorieën.

**Acceptatie:**

- `root_debug_scripts` is 0 of afwezig in de inventaris.
- Geen wijziging in `backend/app` productielogica.
- Geen wijziging in baseline V10.
- Swagger baselinevalidatie blijft groen.

### RR-05 — Legacy patchtools

**Status:** DONE

**Probleem:** tijdelijke patchscripts bleven na uitvoering in `tools/` staan.

**Uitgevoerd:**

- 69 niet-gerefereerde legacy patchtools verwijderd.
- 4 geblokkeerde legacy tools apart beoordeeld.
- Verouderde R9-06 en R9-32G wrappers/tools verwijderd.
- `tools/r7c33_receipt_validation_runner.py` geclassificeerd als `tools_active`.
- Laatste legacy patchtool `tools/patch_dedicated_picnic_eml_import_route.py` verwijderd.
- Python-inventaris opnieuw gegenereerd.
- `tools_legacy_patch` is verdwenen uit de inventariscategorieën.

**Acceptatie:**

- `tools_legacy_patch` is 0 of afwezig in de inventaris.
- Geen wijziging in `backend/app` productielogica.
- Geen wijziging in baseline V10.
- Swagger baselinevalidatie blijft groen.

### RR-06 — Reports/tmp Python-bestanden

**Status:** READY_FOR_LOCAL_EXECUTION

**Probleem:** tijdelijke rapportagebestanden staan nog in de repository en vervuilen de Python-inventaris.

**Bewijs uit inventaris:**

- `reports_tmp`: 9 Python-bestanden.
- Deze categorie is bedoeld voor tijdelijke rapportage- en scratchbestanden.
- Deze categorie hoort niet bij productie-runtime.

**Beheerste verwijdering:**

Gebruik:

```powershell
python tools\cleanup_reports_tmp.py
```

Het script:

1. leest `docs/technical/_generated/python-file-inventory.json`;
2. selecteert alleen items met `repository_category = reports_tmp`;
3. controleert externe verwijzingen buiten toegestane documentatie/tooling, `tools/debug_output/`, `reports/` en `tmp/`;
4. verwijdert alleen niet-gerefereerde kandidaten;
5. laat geblokkeerde kandidaten staan met reden;
6. genereert daarna `docs/technical/_generated/python-file-inventory.*` opnieuw.

**Acceptatie:**

- `reports_tmp` is 0 of afwezig, of resterende bestanden zijn expliciet geblokkeerd met reden.
- Geen wijziging in `backend/app` productielogica.
- Geen wijziging in baseline V10.
- Swagger baselinevalidatie blijft groen.

## Prioriteit 3 — API-laag splitsen

### RR-07 — `backend/app/main.py`

**Status:** split

**Probleem:** te veel routes en verantwoordelijkheden in één bestand.

**Doelstructuur:**

- `backend/app/api/routes/receipts.py`
- `backend/app/api/routes/receipt_sources.py`
- `backend/app/api/routes/gmail.py`
- `backend/app/api/routes/admin_receipts.py`
- `backend/app/api/routes/testing_diagnostics.py`

**Regel:** endpointpaden, requestmodellen en responsecontracten blijven ongewijzigd.

## Prioriteit 4 — Parserlaag structureren

### RR-08 — `backend/app/receipt_ingestion/service_parts/store_specific_parsers.py`

**Status:** split

**Probleem:** winkel-specifieke logica groeit door elkaar.

**Doelstructuur:**

- `backend/app/receipt_ingestion/parsers/picnic_email.py`
- `backend/app/receipt_ingestion/parsers/lidl_app.py`
- `backend/app/receipt_ingestion/parsers/jumbo.py`
- `backend/app/receipt_ingestion/parsers/ah.py`
- `backend/app/receipt_ingestion/parsers/plus.py`
- `backend/app/receipt_ingestion/parsers/aldi.py`

**Regel:** parser outputcontract blijft gelijk.

## Prioriteit 5 — Diagnose/test isoleren

### RR-09 — Testing en diagnose routes

**Status:** move/split

**Probleem:** diagnose- en testendpoints zijn deels vermengd met productie-API.

**Doel:** alle test/diagnose endpoints expliciet onder `testing_diagnostics` router en `diagnostic-only` classificatie.

## Geen acties in deze roadmap zonder akkoord

Niet verwijderen zonder aparte PR:

- databasekolommen zoals `parse_status`;
- baselinebestanden;
- raw testfixtures;
- diagnose endpoints die nog nodig zijn voor releasecontrole.
