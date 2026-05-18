# R7a — Onderhoudbaarheidsanalyse Kassa-inleesproces

## Status

Analyse-opdracht. Geen functionele codewijziging.

## Doel

De bestaande programmatuur voor het inlezen van kassabonnen onderhoudbaarder maken door eerst de huidige flow, verantwoordelijkheden, risico’s en refactor-roadmap vast te leggen.

## Onderzochte scope

Minimaal bekeken/meegewogen:

- `backend/app/services/receipt_service.py`
- `backend/app/receipt_ingestion/product_candidate_gateway.py`
- `backend/app/receipt_ingestion/parser_debug_serializer.py`
- `backend/app/services/receipt_status_baseline_service_v4.py`
- `backend/app/services/receipt_ssot_status.py`
- `backend/app/api/receipt_import_diagnosis_routes.py`
- `backend/app/api/receipt_ingestion_review_routes.py`
- `frontend/src/features/receipts/KassaPage.jsx`
- `frontend/src/pages/ReceiptReviewPreviewPage.jsx`

## 1. Functionele flowkaart

### 1. Upload/import

Hoofdingang voor bonnen:

1. frontend uploadt bestand vanuit Kassa;
2. backend detecteert MIME/type;
3. duplicate check op hash/fingerprint;
4. raw receipt wordt opgeslagen;
5. parserresultaat wordt omgezet naar `receipt_tables` en `receipt_table_lines`.

Belangrijk knooppunt:

- `ingest_receipt(...)` in `receipt_service.py` doet momenteel zowel:
  - MIME-detectie;
  - duplicate-detectie;
  - opslag raw file;
  - parsing aanroepen;
  - database inserts;
  - parser-debug response bouwen.

### 2. OCR/text extractie

`parse_receipt_content(...)` kiest route op basis van MIME/extensie:

- PDF;
- afbeelding;
- HTML/text/email;
- store-specific parsers;
- fallback naar generieke text-line parser.

OCR en parsing zitten nog grotendeels in dezelfde servicefile verweven.

### 3. Parser

Generieke parserroute:

- `_parse_result_from_text_lines(...)`
- winkelherkenning;
- datumherkenning;
- totaalbedragherkenning;
- artikelregel-extractie;
- korting/savings action regels;
- filtering;
- fallbackregels;
- parse-status-inschatting.

### 4. Product candidate gateway

Er is al een goede onderhoudbaarheidsstap gezet:

- `append_product_candidate(...)` is een centrale append-gateway.
- Deze gateway is expliciet parser-status-neutraal.
- Hij beslist alleen of een regel productkandidaat mag worden en voegt producer trace toe.

Dit is een goed patroon voor verdere refactoring.

### 5. Structured parser gateway

Structured parsers voor o.a. PDF/email-resultaten zijn deels via `append_structured_product_candidate(...)` geleid. Dit is eveneens een goed patroon, maar nog niet volledig doorgevoerd voor alle routes.

### 6. Parserdiagnose/debug

Parserdiagnose wordt opgebouwd via:

- `parser_diagnostics.py`
- `parser_debug_serializer.py`
- `producer_trace` op regels.

Dit is nuttig, maar de diagnosevelden zijn nog technisch en niet overal PO-vriendelijk vertaald.

### 7. Statuslaag

Status hoort SSOT te zijn en niet door parser/fallback te worden bepaald. Toch zijn er nog meerdere statusachtige bronnen zichtbaar:

- `parse_status` op `ReceiptParseResult`;
- `receipt_tables.parse_status`;
- PO-normalisatie in `receipt_status_baseline_service_v4.py`;
- `receipt_ssot_status.py`;
- frontend `normalizeInboxStatus(...)`.

R6 heeft veel `manual/Handmatig` verwijderd, maar de recente regressie toont dat statusherberekening en statusweergave nog onvoldoende geïsoleerd zijn.

### 8. Kassa frontend

`KassaPage.jsx` bevat veel verantwoordelijkheden:

- upload UI;
- drag/drop;
- camera-upload;
- e-mail upload;
- inboxlijst;
- statuskaarten;
- detailweergave;
- bonregels;
- preview;
- filtering/sorting;
- foutmeldingen.

Dit maakt frontendwijzigingen risicovol.

## 2. Verantwoordelijkheden per bestand

### `receipt_service.py`

Huidige verantwoordelijkheden:

- bestandsdetectie;
- OCR/text extractie;
- parsing;
- winkel-specifieke extractie;
- fallbackregels;
- duplicate-detectie;
- raw file storage;
- database writes;
- reparse/repair;
- responseopbouw;
- debugpayload koppelen.

Beoordeling:

- Te veel verantwoordelijkheden in één bestand.
- Grootste onderhoudbaarheidsrisico in de receipt lifecycle.

Wat hoort hier uiteindelijk nog thuis:

- orchestration op hoog niveau;
- geen parserdetails;
- geen winkelregels;
- geen fallbackbeleid;
- geen statusbeslissing.

### `backend/app/receipt_ingestion/*`

Huidige verantwoordelijkheden:

- candidate gateways;
- line classification;
- parserdiagnostics;
- debug serializer.

Beoordeling:

- Dit is de juiste richting.
- De module moet de toekomstige standaardlocatie worden voor receipt ingestion engine-logica.

### `receipt_status_baseline_service_v4.py`

Huidige verantwoordelijkheden:

- baseline vergelijken;
- PO-norm bepalen;
- statuslabel afleiden;
- diagnose over statusverschillen.

Beoordeling:

- Belangrijk als SSOT/PO-norm, maar te veel verweven met baseline-testdata.
- Moet niet automatisch historische statusdegradaties veroorzaken.

### `receipt_ssot_status.py`

Huidige verantwoordelijkheden:

- Kassa-payloads ontdoen van parserstatusvelden;
- PO-status op payload toepassen.

Beoordeling:

- Juiste plek voor statuscontract.
- Moet expliciet onderscheid maken tussen:
  - technische parse-status;
  - PO-status;
  - bestaande gebruikerstoestand zoals “Gecontroleerd”.

### `receipt_import_diagnosis_routes.py`

Huidige verantwoordelijkheden:

- diagnose van importgedrag zonder databasewrite;
- expected behavior per bestand.

Beoordeling:

- Nuttig voor PO/diagnose.
- Benamingen moeten statusneutraal blijven.
- Moet geen eigen statusbeleid vormen.

### `receipt_ingestion_review_routes.py`

Huidige verantwoordelijkheden:

- POC/test-run JSONs lezen;
- explainability;
- readiness labels;
- reviewdiagnose.

Beoordeling:

- POC/reviewfunctie is nuttig, maar moet gescheiden blijven van productie-statuslogica.

### `KassaPage.jsx`

Huidige verantwoordelijkheden:

- te breed: upload, lijst, status, detail, preview en editing.

Beoordeling:

- Hoofdkandidaat voor latere frontend-splitsing.

## 3. Risicoplekken

### Risico 1 — monolithische `receipt_service.py`

Het bestand bevat zowel lage OCR/parserdetails als opslag en API-resultaatopbouw. Hierdoor heeft een kleine wijziging aan parser/fallback snel neveneffecten in opslag of status.

### Risico 2 — statusvelden lopen door elkaar

Er bestaan meerdere statusconcepten:

- technische parse-status;
- PO-normstatus;
- inboxstatus;
- bestaande goedkeuring door gebruiker;
- frontend-normalisatie.

Recente regressie waarbij gecontroleerde bonnen degradeerden bewijst dat dit risico reëel is.

### Risico 3 — fallbackregels zijn hardcoded

Voorbeeld:

- bestandsnaam-specifieke fallback zoals Jumbo foto 3.

Risico:

- lastig vindbaar;
- slecht schaalbaar;
- kan diagnose/status beïnvloeden;
- moeilijk te verwijderen als OCR verbetert.

### Risico 4 — winkel-specifieke parserlogica verspreid

Store-specific parsers zitten deels in één servicefile en deels via structured gateway. Dit maakt uitbreiding per winkelketen kwetsbaar.

### Risico 5 — debug/diagnose is technisch goed maar productmatig versnipperd

Er is producer trace, parser debug en readinessdiagnose, maar PO-vriendelijke presentatie is nog niet volledig gestandaardiseerd.

### Risico 6 — frontend Kassa is te groot

`KassaPage.jsx` bevat veel uiteenlopende UI- en dataverantwoordelijkheden. Hierdoor kan een statuskaartwijziging invloed lijken te hebben op upload, detail of preview.

### Risico 7 — tests/tooling niet eenduidig uitvoerbaar

`pytest` is niet beschikbaar in de backendcontainer. Daardoor zijn guardtests niet direct lokaal uitvoerbaar via Docker.

## 4. Refactor-roadmap

### R7b — receipt_service opdelen in orchestration + modules

Doel:

- `receipt_service.py` blijft alleen orchestrator.

Voorstel modules:

```text
backend/app/receipt_ingestion/
  content_detection.py
  extraction_routes.py
  parsing/
    generic_text_parser.py
    store_specific/
  fallbacks/
    fallback_policy.py
  persistence/
    receipt_repository.py
  diagnostics/
    parser_debug_serializer.py
```

Acceptatie:

- geen functionele wijziging;
- bestaande imports blijven werken;
- `ingest_receipt(...)` roept modules aan in plaats van alles zelf te doen.

### R7c — statuscontract expliciet afschermen

Doel:

- parser mag nooit Kassa-status bepalen.
- `parse_status` wordt alleen technische diagnose.
- `inbox_status` komt alleen uit SSOT/persistent user state.

Concrete stap:

- introduceer één statuscontractbestand:

```text
backend/app/services/receipt_status_contract.py
```

Met toegestane waarden:

```text
Gecontroleerd
Controle nodig
```

En expliciete mappingregels.

### R7d — fallback-policy centraliseren

Doel:

- alle fallbackregels weg uit generieke parserfunctie.

Nieuwe plek:

```text
backend/app/receipt_ingestion/fallbacks/fallback_policy.py
```

Per fallback vastleggen:

- id;
- scope;
- reden;
- activeringsvoorwaarde;
- output;
- diagnosemelding;
- expiry/removal condition.

### R7e — winkelprofielen verder uitbouwen

Doel:

- winkel-specifieke parsing niet meer verspreid.

Voorstel:

```text
backend/app/receipt_ingestion/profiles/
  base.py
  aldi.py
  ah.py
  jumbo.py
  lidl.py
  plus.py
  action.py
  gamma.py
  hornbach.py
  bol.py
```

### R7f — diagnose-output standaardiseren

Doel:

- één serializer voor technische debug;
- één translator voor PO-vriendelijke diagnose.

Voorstel:

```text
parser_debug_serializer.py
po_diagnosis_translator.py
```

### R7g — frontend Kassa splitsen

Doel:

`KassaPage.jsx` opdelen in:

```text
ReceiptUploadPanel.jsx
ReceiptInboxSummary.jsx
ReceiptInboxTable.jsx
ReceiptDetailView.jsx
ReceiptPreviewCard.jsx
ReceiptPoDiagnosisCard.jsx
useReceiptInbox.js
useReceiptUpload.js
```

### R7h — regressietestset en tooling herstel

Doel:

- vaste 14 kassabonnen als regressieset;
- commandoregel die gebruiker kan draaien;
- pytest of alternatief beschikbaar in backendcontainer.

Voorstel:

```powershell
docker compose exec backend python -m pytest backend/tests
```

moet werken.

## 5. Acceptatiecriteria onderhoudbaarheid

Nieuwe/refactored code moet aan deze criteria voldoen:

1. Parser bepaalt geen Kassa-status.
2. Fallbacks zijn traceerbaar en centraal geregistreerd.
3. Geen actieve legacy-statussen zoals `manual/Handmatig`.
4. Store-specific regels zitten in profielen of store-specific parsermodules.
5. Debug/diagnose is read-only en verandert geen gedrag.
6. `receipt_service.py` bevat geen nieuwe winkel-specifieke uitzonderingen.
7. Frontendstatuskaarten lezen alleen SSOT-statuslabels.
8. Regressietestset detecteert statusdegradatie.
9. Guardtests zijn lokaal uitvoerbaar in Docker.
10. Elke refactorstap is klein, omkeerbaar en zonder functionele wijziging tenzij expliciet benoemd.

## 6. Aanbevolen volgende opdracht

Start met R7b, maar beperk de eerste stap tot extractie zonder gedrag te wijzigen:

```text
R7b — introduceer receipt ingestion module boundaries en verplaats alleen pure helperfuncties uit receipt_service.py naar receipt_ingestion, zonder functionele wijziging.
```

Eerste veilige sub-stap:

```text
R7b-1 — maak een inventaris van pure helperfuncties in receipt_service.py die zonder database, OCR-state of statuscontext verplaatst kunnen worden.
```

Daarna pas code verplaatsen.
