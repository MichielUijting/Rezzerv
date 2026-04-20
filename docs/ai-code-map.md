# Rezzerv AI Code Map
Laatst bijgewerkt: 2026-04-20

Doel:
Deze map helpt AI-ondersteuning gericht en veilig wijzigingen in de Rezzerv-codebase door te voeren zonder te hoeven gokken naar entrypoints, flows of integratiepunten.

Belangrijke regel:
- GitHub is leidend
- Deze code map moet actueel blijven bij structurele wijzigingen
- Bij verplaatsing van logica moet dit document in dezelfde wijziging mee bijgewerkt worden

---

## 1. Repository basis

Repository:
- `MichielUijting/Rezzerv`

Standaard branch:
- `main`

Releasebeleid:
- Eén release = één hoofddoel
- Geen gemengde releasecategorieën
- Geen breaking change zonder expliciete markering
- Geen release zonder Scope Gate + QA/QC Gate + Packaging Gate groen

Relevante projectregels:
- Bestaande functionaliteit mag niet stilzwijgend breken
- Bestaande parser mag alleen aangepast worden als dat expliciet is goedgekeurd
- Nieuwe preprocessing of filtering bij kassabonnen moet vóór parsing plaatsvinden
- Debug/log-uitbreiding mag bestaande flow niet verdringen

---

## 2. Hoofdstructuur codebase

### Backend
- FastAPI app entrypoint:
  - `backend/app/main.py`

- API routes:
  - `backend/app/main.py`
  - aanvullende routerlaag voor debug: `backend/app/api/router.py` en `backend/app/api/routes/debug.py`

- Services:
  - `backend/app/services/`

- Receipt / OCR / parsing kern:
  - `backend/app/services/receipt_service.py`

- Regressie- en parsingtests:
  - `backend/app/testing/`
  - `backend/app/testing/receipt_parsing/`

- Database/config:
  - `backend/app/db.py`

### Frontend
- App entry:
  - `frontend/src/main.jsx`
  - `frontend/src/App.jsx`

- Router:
  - `frontend/src/app/router/AppRouter.jsx`

- App shell / layout:
  - `frontend/src/app/AppShell.jsx`
  - `frontend/src/ui/Header.jsx`

- Receipt/kassabon UI:
  - overzicht: `frontend/src/features/stores/ReceiptsPage.jsx`
  - detail/importbatch: `frontend/src/features/stores/StoreBatchDetailPage.jsx`
  - kassa/nieuwe kassabon: `frontend/src/features/receipts/KassaPage.jsx`
  - importpagina: `frontend/src/features/stores/StoresPage.jsx`

### Database / models
- ORM models:
  - `backend/app/models/`

- Migraties:
  - geen Alembic-structuur aangetroffen; schema-opbouw en schema-upgrades gebeuren in `backend/app/main.py`

- Runtime database pad:
  - Docker/runtime: `/app/data/rezzerv.db`
  - projectpad lokaal: `backend/data/rezzerv.db`
  - configuratiebron: `backend/app/db.py`
  - volume-koppeling: `docker-compose.yml` mount `./backend/data:/app/data`

---

## 3. Kritieke backend entrypoints

### Receipt upload / import entrypoint
- Bestand:
  - `backend/app/main.py`
- Functie(s):
  - hoofd-API voor kassabonnen staat in `main.py`
  - import flow gebruikt servicefuncties uit `receipt_service.py`

### OCR entrypoint
- Bestand:
  - `backend/app/services/receipt_service.py`
- Functie(s):
  - `_ocr_pdf_text_with_ocrmypdf`
  - `_get_paddle_ocr`
  - `_ocr_image_text_with_paddle`
  - `_ocr_image_text_with_tesseract`

### Receipt parser entrypoint
- Bestand:
  - `backend/app/services/receipt_service.py`
- Functie(s):
  - `parse_receipt_content(file_bytes, filename, mime_type)`
  - interne parsing op OCR/textlijnen via `_parse_result_from_text_lines(...)`

### Voorraad-import vanuit receipt
- Bestand:
  - `backend/app/main.py`
- Functie(s):
  - receipt approval en verwerking richting import/voorraad zit in de receipt endpoints in `main.py`
  - receipt line synchronisatie gebruikt `sync_receipt_table_line_product_links(...)`

### Debug/export van parse-resultaat
- Bestand:
  - `backend/app/api/routes/debug.py`
- Functie(s):
  - `export_receipt_debug(...)`

---

## 4. Kassabonverwerkingsflow

1. Upload afbeelding / bestand
   - Bestand: `backend/app/main.py`
   - Functie: FastAPI receipt endpoints in `main.py`

2. Opslag raw receipt
   - Bestand: `backend/app/services/receipt_service.py`
   - Functie: `ingest_receipt(...)`
   - opslaghelper: `_store_raw_file(...)`

3. OCR op afbeelding of PDF
   - Bestand: `backend/app/services/receipt_service.py`
   - Functie:
     - `_ocr_pdf_text_with_ocrmypdf(...)`
     - `_ocr_image_text_with_paddle(...)`
     - `_ocr_image_text_with_tesseract(...)`

4. Parsing van OCR output
   - Bestand: `backend/app/services/receipt_service.py`
   - Functie:
     - `parse_receipt_content(...)`
     - interne line parsing via `_parse_result_from_text_lines(...)`

5. Mapping naar receipt tables en receipt lines
   - Bestand: `backend/app/services/receipt_service.py`
   - Functie:
     - `ingest_receipt(...)`
     - `reparse_receipt(...)`

6. Handmatige review / correctie
   - Bestand: `backend/app/main.py`
   - Functie:
     - `get_receipt_detail(...)`
     - `update_receipt_header(...)`
     - `update_receipt_line(...)`
     - `create_receipt_line(...)`
     - `approve_receipt_table(...)`
     - `reparse_receipt_table(...)`

7. Import naar voorraad
   - Bestand: `backend/app/main.py`
   - Functie:
     - approval en purchase-import/logica in `main.py`
     - koppeling van receipt lines naar product/article via `sync_receipt_table_line_product_links(...)`

### Belangrijke ontwerpregel voor receipt flow
- Preprocessing mag vóór OCR / vóór parser
- Segmentatie mag vóór parser
- Bestaande parser niet herschrijven zonder expliciete PO-goedkeuring
- Fallback-flow moet behouden blijven

---

## 5. Parser-afbakening

### Parserbestand
- Bestand:
  - `backend/app/services/receipt_service.py`

### Parser input
- Verwacht type:
  - `bytes + filename + mime_type` op publieks-API niveau via `parse_receipt_content(...)`
  - intern verder naar genormaliseerde tekstregels (`list[str]`) voor `_parse_result_from_text_lines(...)`

### Parser output
- Verwacht type:
  - `ReceiptParseResult`

### Hard constraints
- Niet wijzigen zonder expliciete opdracht:
  - `ReceiptParseResult` contract
  - bestaande opslagflow in `ingest_receipt(...)`
  - bestaande reparatieflow in `reparse_receipt(...)`
  - bestaande review- en approvalflow in `main.py`

### Toegestane wijzigingen zonder parser rewrite
- Preprocessing vóór parser
- OCR cleaning vóór parser
- Segmentatie vóór parser
- Ruisfiltering vóór parser
- Debug-uitbreiding naast parser

---

## 6. OCR-specificatie

### OCR engine(s)
- Tesseract:
  - JA
- PaddleOCR:
  - JA
- OCRmyPDF voor PDF OCR:
  - JA

### Adapter / normalisatiebestand
- Bestand:
  - `backend/app/services/receipt_service.py`

### OCR line format
Interne parsing werkt uiteindelijk op genormaliseerde tekstregels (`list[str]`).
De OCR-hulpfuncties gebruiken bbox/anchors intern voor groepering, maar de parserlaag consumeert nu tekstregels.

### Bekende OCR-problemen
- scheef gefotografeerde bonnen
- betaal-/footerregels die als artikelregel eindigen
- sparse OCR waarbij te weinig productregels overblijven
- dubbele/ruisregels uit gemengde foto’s of tweede bon in beeld

---

## 7. Debug en logging

### Debug export receipt parsing
- Bestand:
  - `backend/app/api/routes/debug.py`

### Logbestanden
- primair via runtime logging van backend
- aanvullende diagnostische scripts in repo-root en backend-root

### Wat standaard gelogd mag worden
- preprocess success/failure
- segmentatie aantallen
- OCR regelcount
- parse confidence
- fallback gebruik

### Wat niet stilzwijgend mag verdwijnen
- bestaande debugvelden
- bestaande foutmeldingen
- bestaande reviewstatussen
- `reparsed_from_source` in debug-export

---

## 8. Test- en validatiepunten

### Backend start
- Commando:
  - `docker compose up -d --build`
  - of lokaal: `backend/start-local.sh`
  - of Windows: `backend/start-local.bat`

### Tests
- Commando:
  - `python backend/run-tests.py almost-out`
  - `python backend/run-tests.py product-enrichment`

### Receipt parsing smoke / regressie
- Commando of script:
  - `backend/run-receipt-po-regression.bat`
  - receipt baseline suite via `backend/app/services/receipt_baseline_service.py`
  - fixtures in `backend/app/testing/receipt_parsing/`

### Lokale validatie
- Health endpoint:
  - backend draait op `:8000` in container
  - compose mapped naar host `:8011`

### Verplichte regressie bij receiptwijzigingen
- upload receipt
- OCR draait
- parse-resultaat komt terug
- handmatige review blijft werken
- import naar voorraad blijft werken
- debug-export blijft beschikbaar

---

## 9. Wijzigingsregels voor AI

### AI mag zelfstandig
- nieuwe servicebestanden toevoegen
- imports aanpassen
- bestaande flow uitbreiden met pre-step
- debugvelden toevoegen
- feature branch voorstellen
- regressierisico benoemen
- docs/ai-code-map.md actualiseren

### AI mag niet zelfstandig
- database schema wijzigen zonder expliciete opdracht
- frontend routes wijzigen bij backendopdracht
- parser herschrijven als alleen preprocessing gevraagd is
- bestaande werkende flow vervangen zonder fallback
- release/mijlpaal autonoom vastzetten

---

## 10. Bekende gevoelige onderdelen

- Login flow:
  - `frontend/src/features/auth/LoginPage.jsx`
  - router in `frontend/src/app/router/AppRouter.jsx`

- Receipt parsing:
  - `backend/app/services/receipt_service.py`

- Voorraadtoevoeging:
  - `frontend/src/pages/Voorraad.jsx`
  - backend verwerking in `backend/app/main.py`

- Instellingen/persistentie:
  - settings routes in `frontend/src/app/router/AppRouter.jsx`
  - backend runtime DB in `backend/data/rezzerv.db`

- Build/runtime afhankelijkheden:
  - `docker-compose.yml`
  - `backend/Dockerfile`
  - `frontend/Dockerfile`

---

## 11. Branch- en patchafspraken

Bij AI-opdrachten altijd vermelden:
- repo
- branch
- wijzigingsdoel
- relevante entrypoints

Voorbeeld:
- Repo: `MichielUijting/Rezzerv`
- Branch: `main`
- Doel: preprocessing vóór receipt parser
- Entry points:
  - `backend/app/main.py`
  - `backend/app/services/receipt_service.py`
  - `backend/app/api/routes/debug.py`

---

## 12. Open onderhoudspunt

Dit document moet mee-updaten wanneer:
- bestanden verhuizen
- parserentrypoint wijzigt
- OCR engine wijzigt
- importflow wijzigt
- debug/exportlocatie wijzigt
- API routes wijzigen
