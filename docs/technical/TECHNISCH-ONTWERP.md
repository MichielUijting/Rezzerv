# Rezzerv — Technisch Ontwerp

Status: v0.1 — architectuur- en traceabilitybasis
Scope: backend Python, API, receipt ingestion, status/SSOT, diagnose en testhulpmiddelen

## 1. Doel

Dit technisch ontwerp beschrijft de rol, relatie en positie van de Python-programma's in Rezzerv. Het document is leidend voor:

- onderhoudbaarheid;
- controlled refactoring;
- SSOT-borging;
- opsporen van dode code;
- scheiding tussen productiecode, diagnosecode en testcode.

Elke Python-module moet herleidbaar zijn naar een sectie in dit technisch ontwerp. Omgekeerd moet elke ontwerpsectie verwijzen naar de modules die de verantwoordelijkheid uitvoeren.

## 2. Architectuurprincipes

### 2.1 Single Source of Truth voor kassabonstatus

De functionele status van een kassabon wordt bepaald door de statusbaseline-service. Parserstatus is alleen een technisch diagnoseveld.

Regel:

```text
Parser = data-extractie
Statusbaseline-service = statusbesluit
API/SSOT-mapper = statusvelden voor UI
Frontend = weergave
```

Niet toegestaan:

- status bepalen op basis van bestandsnaam in parser of frontend;
- status bepalen op basis van artikelnaam of bedrag buiten de baseline/statusservice;
- fallbackstatus vanuit `parse_status` gebruiken als functionele UI-status;
- hardcoded bonnamen, artikelnamen of bedragen in productiecode.

Wel toegestaan:

- technische parserdiagnose in debug/explainability;
- baseline- en testdata met concrete boninhoud;
- data-driven criteria in baselinecriteria of testfixtures.

### 2.2 Productie versus diagnose

Diagnosecode mag technische velden tonen, maar mag geen productiegegevens muteren tenzij de route expliciet als repair/migratie is ontworpen en apart is goedgekeurd.

### 2.3 Beheerste refactoring

Refactoring gebeurt in kleine PR's:

1. documenteren;
2. traceability toevoegen;
3. gedrag stabiliseren met tests/Swagger-validatie;
4. code verplaatsen zonder functiewijziging;
5. pas daarna dode code verwijderen.

## 3. Systeemlagen

### TD-01 — Applicatie-overzicht

Rezzerv bestaat technisch uit:

```text
React frontend
  -> FastAPI backend
  -> services en domeinlogica
  -> receipt ingestion/parsers
  -> statusbaseline-service
  -> datastore en raw receipt storage
  -> diagnose/test/admin-routes
```

### TD-02 — Backend API-laag

Verantwoordelijkheid:

- HTTP-contracten;
- requestvalidatie;
- autorisatiecontext;
- aanroepen van services;
- responsevorming.

Belangrijke huidige module:

- `backend/app/main.py`

Architectuurwaarneming:

- `main.py` bevat veel routes en is een duidelijke split-kandidaat.
- Doelstructuur:
  - `backend/app/api/routes/receipts.py`
  - `backend/app/api/routes/receipt_sources.py`
  - `backend/app/api/routes/gmail.py`
  - `backend/app/api/routes/admin_receipts.py`
  - `backend/app/api/routes/testing_diagnostics.py`

Refactorregel:

- Eerst routes verplaatsen met exact dezelfde endpointpaden en responsecontracten.
- Geen functionele wijzigingen tijdens router-split.

### TD-03 — Receipt ingestion en parsers

Verantwoordelijkheid:

- lezen van bronbestanden;
- OCR/MIME/PDF/image verwerking;
- normaliseren van parse-input;
- produceren van kassabonkop en regels;
- bewaren van raw receipt en regels.

Belangrijke modules:

- `backend/app/receipt_ingestion/...`
- `backend/app/receipt_ingestion/service_parts/store_specific_parsers.py`
- `backend/app/receipt_ingestion/structured_product_gateway.py`

Niet toegestaan:

- functionele status bepalen;
- baselinecriteria interpreteren;
- frontendgerichte statusvelden bepalen.

Refactorvraag:

- Kunnen winkel-specifieke parsers worden opgesplitst naar `receipt_ingestion/parsers/<store>.py`?
- Kunnen OCR-, EML- en PDF-adapters los van winkelregels staan?
- Kan product-kandidaatvorming worden gescheiden van bronextractie?

### TD-04 — Status en SSOT

Verantwoordelijkheid:

- bepalen van PO-normstatus;
- toepassen van baselinecriteria;
- leveren van statusvelden aan API/UI;
- scheiden van technische parse-status en functionele status.

Belangrijke modules:

- `backend/app/services/receipt_status_baseline_service/__init__.py`
- `backend/app/services/receipt_ssot_status.py`
- `backend/app/services/receipt_status_baseline_service_v4.py` (compatibility shim, kandidaat-deprecatie)

Regel:

- De statusbaseline-service is de enige bron voor functionele kassabonstatus.
- De SSOT-mapper mag status alleen mappen naar responsevelden, niet zelfstandig herberekenen.

Known cleanup candidates:

- oude runtime-statusfallbacks in `receipt_ssot_status.py`;
- `receipt_status_baseline_service_v4.py` zodra alle imports naar de actieve service verwijzen.

### TD-05 — Datastore en storage

Verantwoordelijkheid:

- databaseverbinding;
- schema/migratie;
- opslag raw receipts;
- transacties.

Moduleclassificatie:

- modules met directe SQL of `engine`-gebruik krijgen `DB_ACCESS=yes` in de modulecatalogus.
- modules die muteren krijgen `WRITES_DATA=yes`.

Ontwerpregel:

- Domeinservices mogen database schrijven.
- Diagnosecode mag read-only zijn tenzij expliciet repair/admin.

### TD-06 — Email, Gmail en inbound routes

Verantwoordelijkheid:

- inbound mailroutes;
- Gmail OAuth en sync;
- mailbronregistratie;
- MIME/EML-broncontext.

Refactorvraag:

- Scheid Gmail-accountbeheer, inbound-webhook en handmatige EML-upload in aparte routes/services.

### TD-07 — Diagnose en explainability

Verantwoordelijkheid:

- zichtbaar maken waarom parser of status tot een resultaat kwam;
- read-only rapportage;
- raw/parser/debug exports.

Regel:

- Diagnose mag technische status tonen als `technical_parse_status` of in een `technical`-blok.
- Diagnose mag geen functionele status bepalen of overschrijven.

### TD-08 — Test, baseline en regressie

Verantwoordelijkheid:

- baselinebestanden;
- testfixtures;
- regression raw files;
- scripts voor validatie of inventarisatie.

Regel:

- Concrete bonbestandsnamen, artikelnamen en bedragen mogen hier voorkomen.
- Ze mogen niet voorkomen in productiecode als beslislogica.

### TD-09 — Tools en scripts

Verantwoordelijkheid:

- eenmalige patchscripts;
- inventarisatiescripts;
- migratiehulpen;
- analysehulpen.

Regel:

- Patchscripts met tijdelijke rol krijgen `DEPRECATE` of `REMOVE_CANDIDATE` zodra de patch verwerkt is.

## 4. Traceability-regel

Elke Python-module krijgt bovenin een compacte verwijzing:

```python
"""
Technical Design Reference:
- TD Section: TD-xx <naam>
- Module Role: <rol>
- Runtime Type: production | diagnostic | test | tool | migration | compatibility
- Used By: <belangrijkste aanroepers>
- Depends On: <belangrijkste afhankelijkheden>
- Reads Data: yes/no
- Writes Data: yes/no
- Status Authority: yes/no
- Refactor Status: keep | split | move | deprecate | remove-candidate
"""
```

## 5. Beslisregels voor dode code

Een module/functie mag pas worden verwijderd wanneer:

1. de module in `PYTHON-MODULE-CATALOG.md` staat;
2. imports/aanroepers zijn geïnventariseerd;
3. er geen productieroute afhankelijk van is;
4. Swagger/PO-validatie groen blijft;
5. de verwijdering in `REFACTOR-ROADMAP.md` als `REMOVE_APPROVED` is gemarkeerd.

## 6. Eerste bekende refactor-kandidaten

| Module | Voorlopig oordeel | Reden |
|---|---|---|
| `backend/app/main.py` | SPLIT | te veel routes en verantwoordelijkheden |
| `backend/app/services/receipt_ssot_status.py` | CLEANUP | bevat oude fallbackstatuslogica |
| `backend/app/services/receipt_status_baseline_service_v4.py` | DEPRECATE | compatibility shim met verwarrende naam |
| `backend/app/receipt_ingestion/service_parts/store_specific_parsers.py` | SPLIT | winkel-specifieke parserlogica groeit door elkaar |
| testing/diagnose routes | MOVE/SPLIT | productie-API en diagnose beter scheiden |

## 7. Acceptatie voor dit ontwerp

Deze ontwerpbaseline is akkoord wanneer:

- alle `.py`-bestanden geïnventariseerd zijn;
- elk `.py`-bestand aan een TD-sectie gekoppeld is;
- elk `.py`-bestand een header of generated catalog entry heeft;
- refactor-/delete-kandidaten niet direct verwijderd maar gemarkeerd zijn;
- SSOT-regels expliciet geborgd zijn in ontwerp en catalogus.
