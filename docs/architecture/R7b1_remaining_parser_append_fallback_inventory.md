# R7b-1 — Inventaris resterende parser-, append- en fallbackpaden

## Status

Analyse-opdracht. Geen functionele codewijziging.

Deze inventaris sluit aan op de reeds uitgevoerde onderhoudbaarheidsstappen:

- R3: product append routes via `append_product_candidate` geleid.
- R4: parser diagnostics toegevoegd.
- R5: parser debug serializer en optionele debugflow toegevoegd.
- R6: legacy-status `Manual/Handmatig` uit de actieve lifecycle verwijderd of uitgefaseerd.

## Doel

Bepalen welke resterende parser-, append-, discount- en fallbackpaden in `receipt_service.py` nog moeten worden geconsolideerd naar `backend/app/receipt_ingestion/`, zonder opnieuw functioneel gedrag of statuslogica te raken.

## Huidige centrale gateways

### `append_product_candidate`

Bestand:

```text
backend/app/receipt_ingestion/product_candidate_gateway.py
```

Rol:

- bedoeld voor OCR/text-line productkandidaten;
- past line-classifier toe;
- voegt uniforme productvorm en `producer_trace` toe;
- is expliciet parser-status-neutraal.

Beoordeling:

- Goed patroon.
- Verdere text-line appendpaden moeten hierlangs blijven lopen.

### `append_structured_product_candidate`

Bestand:

```text
backend/app/receipt_ingestion/structured_product_gateway.py
```

Rol:

- bedoeld voor PDF/e-mail/store-specific parsers;
- past geen OCR line-classifier toe;
- voegt wel uniforme productvorm en `producer_trace` toe;
- is expliciet status-neutraal.

Beoordeling:

- Goed patroon voor structured parsers.
- Structured parserfuncties in `receipt_service.py` gebruiken deze gateway inmiddels grotendeels.

## Inventaris per pad

### 1. Generieke OCR/text parser

Locatie:

```text
receipt_service.py::_parse_result_from_text_lines(...)
```

Type:

```text
generic parser / orchestration / fallback
```

Huidige appendroute:

- `_extract_receipt_lines(...)`
- `_extract_savings_action_lines(...)`
- productregels daarna filteren, korting toepassen, opnieuw filteren.

Gateway gebruikt:

- deels ja, via onderliggende extractie- en savings-routes.

Diagnose aanwezig:

- ja, via `producer_trace` en `summarize_lines_parser_diagnostics(...)`.

Risico:

- deze functie doet te veel:
  - store detectie;
  - branch detectie;
  - datum/totaal;
  - productextractie;
  - savings/action merge;
  - discount merge;
  - fallback;
  - parse-statushint.

Advies:

```text
Verplaatsen naar receipt_ingestion/parsing/generic_text_parser.py, maar pas na een adapterfase.
```

Eerste veilige stap:

- niet direct verplaatsen;
- eerst een façade maken die dezelfde input/output heeft.

---

### 2. Bestandsnaam-specifieke fallback Jumbo foto 3

Locatie:

```text
receipt_service.py::_parse_result_from_text_lines(...)
```

Type:

```text
fallback
```

Huidige appendroute:

- via `append_product_candidate(...)`.

Gateway gebruikt:

- ja.

Diagnose aanwezig:

- ja, via `producer_trace.append_branch` en `parser_path`.

Risico:

- hardcoded op bestandsnaam;
- niet centraal geregistreerd;
- fallback lijkt functioneel productresultaat maar is eigenlijk noodscenario;
- eerdere naamgeving met `manual_fallback` heeft tot verwarring geleid.

Advies:

```text
Verplaatsen naar receipt_ingestion/fallbacks/fallback_policy.py.
```

Toekomstige vorm:

```text
FallbackPolicy(id='jumbo_foto_3_safe_fallback', condition=..., apply=..., diagnostic=...)
```

Geen gedragswijziging bij verplaatsing.

---

### 3. Savings/action line extractie

Locatie:

```text
receipt_service.py::_extract_savings_action_lines(...)
```

Type:

```text
discount / special line parser
```

Huidige appendroute:

- via `append_product_candidate(...)`.

Gateway gebruikt:

- ja.

Diagnose aanwezig:

- ja, via append branch zoals `savings_action_line`.

Risico:

- semantiek is dubbel: actie-/kortingsregel kan productachtig zijn, maar hoort soms bij discountlogica;
- risico op dubbele regels of verkeerde totaalcontrole.

Advies:

```text
Laten staan tot discount-model expliciet is; daarna verplaatsen naar receipt_ingestion/parsing/discount_lines.py.
```

---

### 4. Discount entries toepassen

Locatie:

```text
receipt_service.py::_extract_discount_entries(...)
receipt_service.py::_apply_discount_entries(...)
```

Type:

```text
discount / total reconciliation
```

Huidige appendroute:

- geen product append;
- mutatie/toepassing op bestaande lijnen.

Gateway gebruikt:

- niet van toepassing.

Diagnose aanwezig:

- beperkt; discount-aanpassingen zijn minder goed traceerbaar dan product candidate appends.

Risico:

- beïnvloedt totaalcontrole en daarmee indirect status/diagnose;
- muterende logica is lastig te testen.

Advies:

```text
Verplaatsen naar receipt_ingestion/reconciliation/discounts.py met expliciete before/after diagnostics.
```

---

### 5. Structured PDF parser: Action

Locatie:

```text
receipt_service.py::_parse_action_pdf_result(...)
```

Type:

```text
store-specific structured parser
```

Huidige appendroute:

- via `append_structured_product_candidate(...)`.

Gateway gebruikt:

- ja.

Diagnose aanwezig:

- ja, via `producer_trace`.

Risico:

- parser staat nog in `receipt_service.py`;
- `_receipt_result_from_manual(...)` naamgeving is legacy en moet statusneutraal blijven/worden.

Advies:

```text
Verplaatsen naar receipt_ingestion/parsing/store_specific/action.py.
```

---

### 6. Structured PDF parser: Gamma

Locatie:

```text
receipt_service.py::_parse_gamma_pdf_result(...)
```

Type:

```text
store-specific structured parser
```

Huidige appendroute:

- via `append_structured_product_candidate(...)`.

Gateway gebruikt:

- ja.

Diagnose aanwezig:

- ja.

Risico:

- barcode/detailregel parsing zit in servicefile.

Advies:

```text
Verplaatsen naar receipt_ingestion/parsing/store_specific/gamma.py.
```

---

### 7. Structured PDF parser: Hornbach

Locatie:

```text
receipt_service.py::_parse_hornbach_pdf_result(...)
```

Type:

```text
store-specific structured parser
```

Huidige appendroute:

- via `append_structured_product_candidate(...)`.

Gateway gebruikt:

- ja.

Diagnose aanwezig:

- ja.

Risico:

- hardcoded artikel-/vrachtkostenpatronen;
- geschikt voor module-isolatie.

Advies:

```text
Verplaatsen naar receipt_ingestion/parsing/store_specific/hornbach.py.
```

---

### 8. Structured PDF parser: Lidl invoice

Locatie:

```text
receipt_service.py::_parse_lidl_invoice_pdf_result(...)
```

Type:

```text
store-specific structured parser
```

Huidige appendroute:

- via `append_structured_product_candidate(...)`.

Gateway gebruikt:

- ja.

Diagnose aanwezig:

- ja.

Risico:

- winkelprofielen bestaan al in de POC-context; deze productieparser staat nog niet in profilemodule.

Advies:

```text
Verplaatsen naar receipt_ingestion/parsing/store_specific/lidl_invoice.py of profiles/lidl.py uitbreiden.
```

---

### 9. Structured email parser: Bol

Locatie:

```text
receipt_service.py::_parse_bol_email_result(...)
```

Type:

```text
store-specific email parser
```

Huidige appendroute:

- via `append_structured_product_candidate(...)`.

Gateway gebruikt:

- ja.

Diagnose aanwezig:

- ja.

Risico:

- email parsing hoort niet in algemene receipt service;
- HTML/text source routing is elders verweven.

Advies:

```text
Verplaatsen naar receipt_ingestion/parsing/email/bol.py.
```

---

### 10. Structured email parser: Picnic

Locatie:

```text
receipt_service.py::_parse_picnic_email_result(...)
receipt_service.py::_parse_picnic_flattened_blocks(...)
```

Type:

```text
store-specific email parser / flattened parser
```

Huidige appendroute:

- via `append_structured_product_candidate(...)`.

Gateway gebruikt:

- ja.

Diagnose aanwezig:

- ja voor appended candidates.

Risico:

- complexe parsing met nested/flattened blocks;
- grote kans op regressies bij kleine tekstwijzigingen;
- duidelijke kandidaat voor isolatie met eigen tests.

Advies:

```text
Verplaatsen naar receipt_ingestion/parsing/email/picnic.py met fixturetests.
```

---

### 11. `_line_dict(...)`

Locatie:

```text
receipt_service.py::_line_dict(...)
```

Type:

```text
legacy product shape helper
```

Huidige appendroute:

- directe dict-opbouw zonder producer_trace.

Gateway gebruikt:

- nee.

Diagnose aanwezig:

- nee of beperkt.

Risico:

- elke resterende call naar `_line_dict(...)` omzeilt gatewaydiagnose;
- kan inconsistent productformaat opleveren.

Advies:

```text
Uitfaseren. Alle resterende calls vervangen door append_structured_product_candidate of append_product_candidate.
```

Prioriteit:

- hoog, want dit is precies de categorie die R3-R5 wilden elimineren.

---

### 12. `_receipt_result_from_manual(...)`

Locatie:

```text
receipt_service.py::_receipt_result_from_manual(...)
```

Type:

```text
legacy result builder / structured fallback result builder
```

Huidige appendroute:

- niet zelf appendend, maar bouwt `ReceiptParseResult`.

Gateway gebruikt:

- afhankelijk van aangeleverde lines.

Diagnose aanwezig:

- ja, via `summarize_lines_parser_diagnostics(lines)`.

Risico:

- naamgeving legacy/verwarrend;
- status- en fallbacktaal lopen semantisch door elkaar.

Advies:

```text
Hernoemen naar _receipt_result_from_structured_source(...) of _receipt_result_from_structured_fallback(...), zonder gedrag te wijzigen.
```

---

### 13. Store-specific routing

Locatie:

```text
receipt_service.py::_parse_store_specific_result(...)
```

Type:

```text
router / orchestration
```

Huidige route:

- roept meerdere store-specific parserfuncties aan.

Gateway gebruikt:

- afhankelijk van onderliggende parser.

Diagnose aanwezig:

- indirect.

Risico:

- routing en parserimplementatie zitten in hetzelfde bestand;
- nieuwe winkelketens vergroten `receipt_service.py` verder.

Advies:

```text
Verplaatsen naar receipt_ingestion/parsing/store_specific/router.py.
```

## Samenvattende risicotabel

| Pad | Gateway | Diagnose | Risico | Advies |
|---|---:|---:|---|---|
| Generic text parser | deels | ja | hoog | adapterfase naar `generic_text_parser.py` |
| Jumbo safe fallback | ja | ja | hoog | centraliseren in fallback policy |
| Savings/action lines | ja | ja | middel | later naar discount_lines |
| Discount entries | n.v.t. | beperkt | hoog | naar reconciliation/discounts |
| Action parser | ja | ja | laag/middel | naar store_specific/action.py |
| Gamma parser | ja | ja | laag/middel | naar store_specific/gamma.py |
| Hornbach parser | ja | ja | middel | naar store_specific/hornbach.py |
| Lidl invoice parser | ja | ja | middel | naar store_specific/lidl_invoice.py |
| Bol parser | ja | ja | middel | naar email/bol.py |
| Picnic parser | ja | ja | hoog | naar email/picnic.py + tests |
| `_line_dict` | nee | nee | hoog | uitfaseren |
| `_receipt_result_from_manual` | n.v.t. | ja | middel | hernoemen |
| store-specific router | deels | indirect | middel | naar routermodule |

## Aanbevolen volgende refactorstappen

### R7b-2 — `_line_dict` volledig uitfaseren

Waarom eerst:

- kleine afgebakende stap;
- sluit direct aan op R3-R5 gatewaystrategie;
- verhoogt diagnoseconsistentie;
- raakt geen statuscontract.

Acceptatie:

- geen `_line_dict(...)` calls meer in `receipt_service.py`;
- alle productregels hebben `producer_trace`;
- geen functionele parserwijziging buiten uniforme metadata.

### R7b-3 — structured result builder hernoemen

Waarom:

- verwijdert verwarrende legacybenaming;
- geen gedragswijziging.

Acceptatie:

- `_receipt_result_from_manual` bestaat niet meer;
- vervangende naam is statusneutraal;
- output blijft identiek.

### R7b-4 — store-specific routermodule introduceren

Waarom:

- maakt latere verplaatsing per winkel mogelijk;
- houdt public API stabiel.

Acceptatie:

- `receipt_service.py` roept router aan;
- parserfuncties mogen tijdelijk nog in servicefile blijven;
- geen functionele wijziging.

### R7b-5 — fallback policy-module introduceren

Waarom:

- hardcoded fallback uit generic parser halen;
- fallback traceerbaar en beheerbaar maken.

Acceptatie:

- Jumbo fallback staat geregistreerd in policy;
- output en producer_trace blijven gelijk;
- status blijft onaangeraakt.

## Niet doen in R7b

- geen statusherberekening;
- geen wijziging aan PO-norm;
- geen nieuwe frontendstatussen;
- geen parserkwaliteit verbeteren;
- geen OCR-route aanpassen.

## Conclusie

De onderhoudbaarheidslijn is helder: R3-R5 hebben append-gateways en diagnostics geïntroduceerd. R7b moet daarop voortbouwen door resterende legacy append/result/fallback-paden uit `receipt_service.py` te halen of eerst statusneutraal te benoemen.

De veiligste volgende stap is:

```text
R7b-2 — _line_dict uitfaseren en resterende directe productdicts via gateways laten lopen.
```
