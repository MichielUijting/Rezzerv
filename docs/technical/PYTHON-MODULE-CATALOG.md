# Rezzerv — Python Module Catalog

Status: v0.1 — handmatige startcatalogus plus gegenereerde inventaris

Dit document bevat per Python-module de rol, laag, status en refactorbeoordeling. De volledige bestandslijst wordt gegenereerd met `tools/generate_python_module_inventory.py`.

## Catalogusvelden

| Veld | Betekenis |
|---|---|
| TD Section | Sectie in `TECHNISCH-ONTWERP.md` |
| Runtime Type | production, diagnostic, test, tool, migration, compatibility |
| Role | primaire verantwoordelijkheid |
| Used By | belangrijkste aanroepers |
| Depends On | belangrijkste afhankelijkheden |
| Reads/Writes Data | database/storagegebruik |
| Status Authority | mag functionele kassabonstatus bepalen? |
| Refactor Status | keep, split, move, deprecate, remove-candidate |

## Kernmodules

### backend/app/main.py

| Veld | Waarde |
|---|---|
| TD Section | TD-02 Backend API-laag |
| Runtime Type | production |
| Role | FastAPI entrypoint en routecontainer |
| Used By | Uvicorn/FastAPI runtime |
| Depends On | services, ingestion, db, auth, testing/admin helpers |
| Reads Data | yes |
| Writes Data | yes |
| Status Authority | no |
| Refactor Status | split |

**Analyse:** `main.py` bevat veel domeinen: receipts, sources, Gmail, admin, diagnostics en mutaties. Dit moet worden opgesplitst in routers met behoud van endpointpaden.

---

### backend/app/services/receipt_status_baseline_service/__init__.py

| Veld | Waarde |
|---|---|
| TD Section | TD-04 Status en SSOT |
| Runtime Type | production |
| Role | Enige bron voor PO-normstatus op basis van baseline en criteria |
| Used By | `receipt_ssot_status.py`, admin validation/diagnose routes |
| Depends On | baseline JSON, criteria overrides, datastore via validatiecontext |
| Reads Data | yes |
| Writes Data | no |
| Status Authority | yes |
| Refactor Status | keep |

**Analyse:** Dit is de statusautoriteit. Concrete criteria mogen data-driven uit baseline/criteria-overrides komen, niet hardcoded in parser of frontend.

---

### backend/app/services/receipt_ssot_status.py

| Veld | Waarde |
|---|---|
| TD Section | TD-04 Status en SSOT |
| Runtime Type | production |
| Role | Mapper van PO-normstatus naar API/UI-statusvelden |
| Used By | receipt list/detail/explainability responses |
| Depends On | `receipt_status_baseline_service` |
| Reads Data | indirectly via statusservice |
| Writes Data | no |
| Status Authority | no, mapper only |
| Refactor Status | cleanup |

**Analyse:** Bevat historisch nog runtime fallbackstatuslogica. Deze functie hoort niet de functionele status te herberekenen. Kandidaten voor cleanup: oude `_r9_38d6_*` fallbackhelpers.

---

### backend/app/services/receipt_status_baseline_service_v4.py

| Veld | Waarde |
|---|---|
| TD Section | TD-04 Status en SSOT |
| Runtime Type | compatibility |
| Role | Legacy importshim naar actieve statusbaseline-service |
| Used By | oude imports, indien nog aanwezig |
| Depends On | `receipt_status_baseline_service` |
| Reads Data | no |
| Writes Data | no |
| Status Authority | no |
| Refactor Status | deprecate |

**Analyse:** Geen oude statuslogica meer, maar naamgeving is misleidend. Eerst imports vervangen, daarna verwijderen.

---

### backend/app/receipt_ingestion/structured_product_gateway.py

| Veld | Waarde |
|---|---|
| TD Section | TD-03 Receipt ingestion en parsers |
| Runtime Type | production |
| Role | Uniform toevoegen van gestructureerde productkandidaten |
| Used By | store-specific parsers |
| Depends On | parserhelpers/callers |
| Reads Data | no |
| Writes Data | no |
| Status Authority | no |
| Refactor Status | keep |

**Analyse:** Productkandidaatvorming mag geen status bepalen. Filters moeten gericht zijn op productkwaliteit, niet PO-status.

---

### backend/app/receipt_ingestion/service_parts/store_specific_parsers.py

| Veld | Waarde |
|---|---|
| TD Section | TD-03 Receipt ingestion en parsers |
| Runtime Type | production |
| Role | Winkel-specifieke parsepatronen en parserroutes |
| Used By | receipt ingestion service |
| Depends On | structured product gateway, parserhelpers |
| Reads Data | no |
| Writes Data | no |
| Status Authority | no |
| Refactor Status | split |

**Analyse:** Kandidaat om te splitsen per winkel of bronfamilie: `picnic_email.py`, `lidl_app.py`, `jumbo.py`, enzovoort.

---

### backend/app/receipt_ingestion/explainability.py

| Veld | Waarde |
|---|---|
| TD Section | TD-07 Diagnose en explainability |
| Runtime Type | diagnostic |
| Role | Read-only uitleg van parserresultaten |
| Used By | explainability endpoint |
| Depends On | ingestion result structures |
| Reads Data | via caller |
| Writes Data | no |
| Status Authority | no |
| Refactor Status | keep_diagnostic |

**Analyse:** Mag technische diagnose tonen, maar geen status muteren.

---

## Generated catalog

De volledige lijst moet worden gegenereerd met:

```powershell
python tools/generate_python_module_inventory.py
```

Output:

```text
docs/technical/_generated/python-file-inventory.md
docs/technical/_generated/python-file-inventory.json
```

Na generatie moeten alle onbekende modules worden aangevuld in deze catalogus of gemarkeerd als `unclassified` in de traceability-matrix.
