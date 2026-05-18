# R6a — Impactanalyse verwijderen Manual/Handmatig uit receipt lifecycle

## Architectuurprincipe

Rezzerv kent geen dode of legacy-statussen in actieve code. Een status die niet functioneel in de app gebruikt wordt, mag niet achterblijven in backend, frontend, diagnose, tests of SSOT.

## Besluit

De status `manual` / `Handmatig` wordt uitgefaseerd als actieve kassabonstatus.

Doelstatussen voor Kassa en receipt lifecycle:

- `approved` / `Gecontroleerd`
- `review_needed` / `Controle nodig`

Alle gevallen die eerder `manual` of `Handmatig` werden, worden functioneel behandeld als `review_needed` / `Controle nodig`, tenzij het aantoonbaar geen status maar een gebruikersactie betreft.

## Classificatie van gevonden hits

### 1. Actief statusconcept — vervangen

Bestanden:

- `backend/app/services/receipt_ssot_status.py`
- `backend/app/services/receipt_status_baseline_service.py`
- `backend/app/services/receipt_status_baseline_service_v4.py`
- `backend/app/services/receipt_status_sync.py`
- `backend/app/services/receipt_parser_quality_patch.py`

Voorbeelden:

- `STATUS_LABELS = {'approved': 'Gecontroleerd', 'review_needed': 'Controle nodig', 'manual': 'Handmatig'}`
- `_status_code('Handmatig') -> 'manual'`
- `result.parse_status = 'manual'`
- counts met `manual`

Actie:

- `manual` verwijderen uit statuslabelsets.
- `Handmatig` niet meer als statuslabel tonen of retourneren.
- parser-/kwaliteitspaden die nu `manual` zetten, omzetten naar `review_needed`.
- status-sync counts aanpassen naar alleen `approved` en `review_needed`.

### 2. Diagnosebeleid — hernoemen en inhoudelijk mappen

Bestand:

- `backend/app/api/receipt_import_diagnosis_routes.py`

Voorbeelden:

- `should_be_manual`
- `create_manual_receipt_when_parse_quality_low`
- beleidstekst: `Gecontroleerd, Controle nodig of Handmatig`

Actie:

- `should_be_manual` hernoemen naar `should_need_review`.
- `create_manual_receipt_when_parse_quality_low` vervangen door `create_review_needed_receipt_when_parse_quality_low`.
- beleidstekst aanpassen naar `Gecontroleerd of Controle nodig`.

### 3. Review-readiness actie — hernoemen, geen status maken

Bestand:

- `backend/app/api/receipt_ingestion_review_routes.py`

Voorbeelden:

- `manual_entry_needed`
- `manual_entry`
- `recommended_user_action: manual_entry`

Classificatie:

Dit is deels een gebruikersactie, maar de naam lijkt op een status en veroorzaakt begripsvervuiling.

Actie:

- Hernoemen naar `user_correction_needed` of `review_input_needed`.
- `recommended_user_action: manual_entry` vervangen door `correct_in_review`.
- Niet mappen naar Kassa-status; Kassa-status blijft `review_needed`.

### 4. Parserfallbacknaam — hernoemen, gedrag behouden

Bestand:

- `backend/app/services/receipt_service.py`

Voorbeelden:

- `manual_lines`
- `jumbo_foto_3_manual_fallback`
- `_receipt_result_from_manual(...)`

Classificatie:

Dit is geen statusconcept, maar de naam communiceert alsnog legacygedrag. Omdat R5 juist diagnose zichtbaar maakt, moeten namen PO-vriendelijk en statusvrij zijn.

Actie:

- `manual_lines` hernoemen naar `fallback_lines`.
- `jumbo_foto_3_manual_fallback` hernoemen naar `jumbo_foto_3_safe_fallback`.
- `_receipt_result_from_manual` hernoemen naar `_receipt_result_from_structured_fallback` of `_receipt_result_from_known_structured_source`.
- Geen gedragswijziging in dezelfde stap; alleen naamgeving en traces corrigeren.

### 5. Testdata/baseline — migreren

Bestanden/paden:

- `backend/app/testing/receipt_status_baseline/expected_status_v6.json`
- tests die `manual` verwachten
- selftests met `manual_test` waar het alleen testnaam is

Actie:

- Alle verwachte `manual` statussen in baseline migreren naar `review_needed`.
- Testnamen alleen aanpassen als ze naar receipt-status verwijzen.
- `manual_test` in productcatalogustest mag voorlopig blijven als het een testprovidernaam is en geen receipt-status.

### 6. Gewone taal/commentaar — selectief aanpassen

Voorbeeld:

- commentaar zoals `artikelregels kunnen later handmatig worden verbeterd`

Classificatie:

Geen statusconcept. Toch liever taalneutraler maken als dit in gebruikersgerichte context verschijnt.

Actie:

- In comments mag `handmatig` blijven als het letterlijk menselijke bewerking betekent.
- In UI/API-responses vervangen door `zelf corrigeren`, `controle nodig` of `correctie nodig`.

## Voorgestelde R6-fasering

### R6b — SSOT statuscontract opschonen

- Verwijder `manual` / `Handmatig` uit `receipt_ssot_status.py` en baseline service v4.
- Alles wat als `Handmatig` uit baseline komt, mappen naar `Controle nodig`.
- Acceptatie: Kassa-payloads bevatten nooit `status: Handmatig`, `inbox_status: Handmatig` of `po_norm_status: manual`.

### R6c — parse-status en quality patch opschonen

- `receipt_parser_quality_patch.py`: `parse_status = 'manual'` vervangen door `review_needed`.
- Oude parse-statuswaarden normaliseren naar `review_needed` waar nodig.
- Acceptatie: nieuwe imports krijgen geen `parse_status='manual'` meer.

### R6d — diagnose-routes hernoemen

- `should_be_manual` -> `should_need_review`.
- `create_manual_receipt_when_parse_quality_low` -> `create_review_needed_receipt_when_parse_quality_low`.
- Beleidsteksten aanpassen.
- Acceptatie: diagnose JSON bevat geen `manual`/`Handmatig` als statusconcept.

### R6e — ingestion review readiness hernoemen

- `manual_entry_needed` -> `user_correction_needed` of `review_input_needed`.
- `manual_entry` -> `correct_in_review`.
- Acceptatie: readiness blijft functioneel gelijk, maar gebruikt geen manual-statusachtige taal.

### R6f — parserfallback-namen opschonen

- `manual_lines` -> `fallback_lines`.
- `jumbo_foto_3_manual_fallback` -> `jumbo_foto_3_safe_fallback`.
- `_receipt_result_from_manual` -> fallback/structured naam.
- Acceptatie: producer_trace bevat geen `manual_fallback` meer.

### R6g — baseline/testmigratie en guardtest

- Baseline-verwachtingen migreren naar `review_needed`.
- Voeg guardtest toe: actieve receipt lifecycle mag geen statuswaarde `manual` of label `Handmatig` teruggeven.
- Acceptatie: test faalt zodra `manual`/`Handmatig` opnieuw als status wordt geïntroduceerd.

## Niet in scope voor R6

- Het verwijderen van gewone menselijke bewerkingsacties zoals artikel toevoegen of corrigeren.
- Het verwijderen van vrije tekstcommentaren waarin `handmatig` letterlijk niet-statusmatig wordt gebruikt.
- Grote UX-herbouw van Kassa buiten de statusopschoning.

## Aanbevolen eerste implementatiestap

Start met R6b: SSOT statuscontract opschonen. Zolang de SSOT nog `manual`/`Handmatig` kent, blijven downstream frontend en diagnose kwetsbaar voor terugkeer van de categorie.
