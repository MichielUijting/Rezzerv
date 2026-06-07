# Rezzerv — Traceability Matrix

Status: v0.1

Deze matrix koppelt ontwerpsecties aan Python-modules. De volledige matrix wordt aangevuld op basis van `tools/generate_python_module_inventory.py`.

## Matrixregels

| TD Section | Verantwoordelijkheid | Module(s) | Runtime Type | Refactorstatus |
|---|---|---|---|---|
| TD-01 Applicatie-overzicht | Systeemcontext | `docs/technical/TECHNISCH-ONTWERP.md` | documentation | keep |
| TD-02 Backend API-laag | HTTP-routes en responsevorming | `backend/app/main.py` | production | split |
| TD-03 Receipt ingestion en parsers | Bronverwerking en productregels | `backend/app/receipt_ingestion/**.py` | production | split/keep |
| TD-04 Status en SSOT | Functionele kassabonstatus | `backend/app/services/receipt_status_baseline_service/__init__.py` | production | keep |
| TD-04 Status en SSOT | UI-statusmapping | `backend/app/services/receipt_ssot_status.py` | production | cleanup |
| TD-04 Status en SSOT | Legacy shim | `backend/app/services/receipt_status_baseline_service_v4.py` | compatibility | deprecate |
| TD-05 Datastore en storage | DB/storage helpers | `backend/app/db*.py`, storage modules | production | classify |
| TD-06 Email, Gmail en inbound | Email routes en sync | Gmail/inbound modules en routes | production | split |
| TD-07 Diagnose en explainability | Read-only analyse | explainability/testing diagnosis modules | diagnostic | keep_diagnostic |
| TD-08 Test, baseline en regressie | Testdata en regressie | `backend/app/testing/**.py`, `tools/**.py` | test/tool | classify |
| TD-09 Tools en scripts | Patch/inventarisatie/migratie | `tools/**.py` | tool | deprecate/remove-candidate per script |

## Bidirectionele traceability

### Van ontwerp naar code

Elke sectie in `TECHNISCH-ONTWERP.md` verwijst naar modules in deze matrix.

### Van code naar ontwerp

Elke Python-module krijgt uiteindelijk een header:

```python
"""
Technical Design Reference:
- TD Section: TD-xx <naam>
- Module Role: <rol>
- Runtime Type: production | diagnostic | test | tool | migration | compatibility
- Refactor Status: keep | split | move | deprecate | remove-candidate
"""
```

## Statuswaarden

| Waarde | Betekenis |
|---|---|
| keep | behouden zoals is |
| keep_diagnostic | bewust behouden als diagnose/test |
| split | module is te groot of heeft meerdere verantwoordelijkheden |
| move | module hoort in andere laag/map |
| cleanup | module behouden, maar dode code verwijderen |
| deprecate | eerst imports vervangen, daarna verwijderen |
| remove-candidate | waarschijnlijk dode code, eerst bewijs verzamelen |
| classify | nog te classificeren na automatische inventarisatie |

## Acceptatie voor volledige matrix

- Geen `.py`-bestand blijft `unclassified`.
- Elk productiepad heeft een TD-sectie.
- Elk statusgerelateerd bestand heeft `Status Authority` expliciet op yes/no.
- Elk diagnosebestand is expliciet `diagnostic` of `test`.
