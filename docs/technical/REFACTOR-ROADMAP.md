# Rezzerv — Refactor Roadmap

Status: v0.1

Deze roadmap ordent refactoring en dead-code-cleanup. Er wordt niets verwijderd zonder traceability en bewijs.

## Werkwijze

1. Inventariseren.
2. Classificeren.
3. Test-/Swagger-bewijs vastleggen.
4. Refactoren zonder functionele wijziging.
5. Dode code verwijderen in aparte cleanup-PR.

## Prioriteit 1 — SSOT/statuslaag opschonen

### RR-01 — `backend/app/services/receipt_ssot_status.py`

**Status:** cleanup

**Probleem:** bevat historische runtime fallbackstatuslogica die functionele status kan afleiden uit parserstatus, totalen en NO_BASELINE_MATCH.

**Gewenste toestand:**

- `apply_po_norm_status` is alleen mapper van statusbaseline-service naar UI/API-velden.
- Geen fallback vanuit `parse_status`.
- Geen `runtime_status_source = parser` voor functionele UI-status.

**Acceptatie:**

- Swagger `validate-receipt-status-baseline` blijft groen.
- Kassa toont status uit `po_norm_status_label`.
- `findstr /S /N /I /C:"_r9_38d6_runtime_status_override" backend\app` geeft geen productiehit.

### RR-02 — `backend/app/services/receipt_status_baseline_service_v4.py`

**Status:** deprecate

**Probleem:** compatibility shim met verwarrende naam.

**Stappen:**

1. Zoek imports naar `receipt_status_baseline_service_v4`.
2. Vervang door `receipt_status_baseline_service`.
3. Verwijder shim pas als grep leeg is.

**Acceptatie:** FastAPI start; baselinevalidatie blijft groen.

## Prioriteit 2 — API-laag splitsen

### RR-03 — `backend/app/main.py`

**Status:** split

**Probleem:** te veel routes en verantwoordelijkheden in één bestand.

**Doelstructuur:**

- `backend/app/api/routes/receipts.py`
- `backend/app/api/routes/receipt_sources.py`
- `backend/app/api/routes/gmail.py`
- `backend/app/api/routes/admin_receipts.py`
- `backend/app/api/routes/testing_diagnostics.py`

**Regel:** endpointpaden, requestmodellen en responsecontracten blijven ongewijzigd.

## Prioriteit 3 — Parserlaag structureren

### RR-04 — `backend/app/receipt_ingestion/service_parts/store_specific_parsers.py`

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

## Prioriteit 4 — Diagnose/test isoleren

### RR-05 — Testing en diagnose routes

**Status:** move/split

**Probleem:** diagnose- en testendpoints zijn deels vermengd met productie-API.

**Doel:** alle test/diagnose endpoints expliciet onder `testing_diagnostics` router en `diagnostic-only` classificatie.

## Prioriteit 5 — Tools opschonen

### RR-06 — Patchscripts in `tools/`

**Status:** classify/deprecate/remove-candidate

**Probleem:** tijdelijke patchscripts blijven na uitvoering in repository staan.

**Regel:**

- scripts die herbruikbaar zijn: documenteren als tool;
- scripts die eenmalig waren: markeren als remove-candidate;
- verwijderen pas na traceability en akkoord.

## Geen acties in deze roadmap zonder akkoord

Niet verwijderen zonder aparte PR:

- databasekolommen zoals `parse_status`;
- baselinebestanden;
- raw testfixtures;
- diagnose endpoints die nog nodig zijn voor releasecontrole.
