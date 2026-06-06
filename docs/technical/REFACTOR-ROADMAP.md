# Rezzerv — Refactor Roadmap

Status: v0.2

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

**Status:** READY_FOR_LOCAL_EXECUTION

**Probleem:** lokale safety-archives staan in Git en vervuilen de actieve Python-inventaris.

**Bewijs uit inventaris:**

- `local_safety_archive`: 68 Python-bestanden.
- Alle bestanden in deze categorie staan op `remove-candidate`.
- Alle bestanden hebben `header_scope_default = false`.
- Deze categorie bevat geen FastAPI-routes.

**Beheerste verwijdering:**

Gebruik:

```powershell
python tools\cleanup_local_safety_archive.py
```

Het script:

1. zoekt `_local_safety_before_sync_*` mappen;
2. controleert externe verwijzingen buiten toegestane documentatie/tooling;
3. verwijdert de mappen alleen als er geen externe verwijzingen zijn;
4. genereert daarna `docs/technical/_generated/python-file-inventory.*` opnieuw.

**Acceptatie:**

- `local_safety_archive` is 0 of afwezig in de inventaris.
- `active_backend_app` blijft functioneel ongewijzigd.
- Geen wijziging in frontend, baseline V10 of productie-parserlogica.
- Swagger baselinevalidatie blijft groen.

### RR-04 — Root debug scripts

**Status:** NEXT_CANDIDATE

**Probleem:** losse root scripts zoals `dump_*`, `peek_*`, `inspect_*` vervuilen de repository.

**Aanpak:** eerst inventariseren en markeren; daarna per script verwijderen of verplaatsen naar `tools/archive/`.

### RR-05 — Legacy patchtools

**Status:** NEXT_CANDIDATE

**Probleem:** tijdelijke patchscripts blijven na uitvoering in `tools/` staan.

**Regel:**

- scripts die herbruikbaar zijn: documenteren als tool;
- scripts die eenmalig waren: markeren als remove-candidate;
- verwijderen pas na traceability en akkoord.

## Prioriteit 3 — API-laag splitsen

### RR-06 — `backend/app/main.py`

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

### RR-07 — `backend/app/receipt_ingestion/service_parts/store_specific_parsers.py`

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

### RR-08 — Testing en diagnose routes

**Status:** move/split

**Probleem:** diagnose- en testendpoints zijn deels vermengd met productie-API.

**Doel:** alle test/diagnose endpoints expliciet onder `testing_diagnostics` router en `diagnostic-only` classificatie.

## Geen acties in deze roadmap zonder akkoord

Niet verwijderen zonder aparte PR:

- databasekolommen zoals `parse_status`;
- baselinebestanden;
- raw testfixtures;
- diagnose endpoints die nog nodig zijn voor releasecontrole.
