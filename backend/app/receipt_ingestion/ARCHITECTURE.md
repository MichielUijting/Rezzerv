# Rezzerv Receipt Ingestion Engine - architectuuranker

Versie: R9-35A
Status: architectuuranker, geen functionele runtime-wijziging

## Doel

De Receipt Ingestion Engine moet onderhoudbaar blijven door een harde scheiding tussen:

1. generieke pipeline/orchestration;
2. technische extractie zoals OCR, PDF-tekst en email/html-tekst;
3. generieke parsing-primitives;
4. winkelspecifieke profielen.

Deze scheiding voorkomt grote ononderhoudbare servicebestanden, verborgen fallbacklogica en winkelregels die verspreid raken door generieke code.

## SSOT-regels

- De parser bepaalt nooit de functionele kassabonstatus.
- De status wordt uitsluitend bepaald door `receipt_status_baseline_service_v4.py`.
- UI en API gebruiken alleen `po_norm_status_label` voor statusweergave.
- Diagnose-exports wijzigen nooit productiegegevens.
- Shadow/reconstructie-rijen worden nooit automatisch productieparserregels.
- Baselinebedragen worden nooit runtime-correcties.
- `total_amount` mag niet worden afgeleid uit de som van artikelregels.
- Artikelregelsommen zijn uitsluitend validatie-input voor PO/statuscontroles.

## Doellagen

### 1. Pipeline

Locatie:

```text
backend/app/receipt_ingestion/pipeline/
```

Verantwoordelijkheid:

- source-kind bepalen;
- OCR/preprocessing/extractie aanroepen;
- winkelprofiel detecteren/selecteren;
- parse-resultaat samenstellen;
- diagnostics verzamelen.

Niet toegestaan:

- winkelketenregels;
- winkelnaam-specifieke regexen;
- filename-hacks;
- statusbepaling;
- inhoudelijke fallback zoals `total_amount = artikelregelsom`.

### 2. Extraction

Locatie:

```text
backend/app/receipt_ingestion/extraction/
```

Verantwoordelijkheid:

- image OCR;
- PDF direct-text en OCR;
- email/html/text extractie;
- technische preprocessing.

Niet toegestaan:

- bepalen welke regel een artikel is;
- bepalen welke regel het kassabontotaal is;
- winkelspecifieke betekenis toekennen;
- status bepalen.

### 3. Core primitives

Locatie:

```text
backend/app/receipt_ingestion/core/
```

Verantwoordelijkheid:

- bedragen parsen;
- tekst normaliseren;
- generieke line-classification helpers;
- product-candidate builders;
- fingerprints;
- parser diagnostics.

Niet toegestaan:

- winkelnaam-specifieke regels;
- store-specific artikelregels;
- store-specific totaalregels.

### 4. Store profiles

Locatie:

```text
backend/app/receipt_ingestion/profiles/
```

Verantwoordelijkheid:

- detectie per winkelketen;
- header/filiaalregels per winkelketen;
- totaalregels per winkelketen;
- artikelregels per winkelketen;
- non-product filters per winkelketen;
- store-specific diagnostics.

Voorbeeldstructuur:

```text
profiles/
  registry.py
  base.py
  ah/
    profile.py
    detect.py
    header.py
    totals.py
    articles.py
    filters.py
    diagnostics.py
  jumbo/
    profile.py
    detect.py
    header.py
    totals.py
    articles.py
    filters.py
  lidl/
    profile.py
    detect.py
    header.py
    totals.py
    articles.py
    invoice_pdf.py
```

## Verboden afhankelijkheden

Generieke modules mogen niet afhankelijk zijn van concrete winkelregels.

Niet toegestaan in generieke bestanden:

```text
Albert Heijn
AH
Jumbo
Lidl
Action
Gamma
Hornbach
Picnic
Bol
```

Uitzondering: profielregistratie in `profiles/registry.py`.

Niet toegestaan:

```python
if filename == "jumbo foto 3.jpg":
    ...
```

Niet toegestaan:

```python
if total_amount is None:
    total_amount = sum(article_lines)
```

## Toegestane verantwoordelijkheden per laag

| Laag | Mag wel | Mag niet |
|---|---|---|
| Pipeline | routeren en orchestreren | winkelbetekenis bepalen |
| Extraction | tekst/OCR produceren | artikels/totaal interpreteren |
| Core | generieke helpers leveren | AH/Jumbo/Lidl-regels bevatten |
| Profiles | winkelbetekenis bepalen | database muteren of status bepalen |
| Status service | status bepalen | parserregels wijzigen |

## Huidige overgangssituatie

R9-35A introduceert het architectuuranker zonder functionele migratie. Bestaande code blijft werken, maar nieuwe wijzigingen moeten deze structuur volgen.

Bekende huidige afwijkingen:

- `receipt_service.py` bevat nog te veel orchestration, parsing en store-specific uitzonderingen.
- `header_parser.py` bevat nog generieke en AH-specifieke header/totaallogica door elkaar.
- `profiles/ah_runtime.py` bevat al AH-artikelregels, maar is nog niet opgesplitst naar `profiles/ah/articles.py`, `profiles/ah/totals.py`, enzovoort.
- Enkele winkel-specifieke PDF/email parsers zitten nog in `receipt_service.py`.
- `store_branch`-extractie is nog generiek en te breed.

## Migratieprincipe

Migratie gebeurt incrementeel en regressieveilig:

1. Eerst documenteren en interfaces plaatsen.
2. Dan per winkelketen een profielstructuur aanmaken.
3. Daarna per verantwoordelijkheid verplaatsen:
   - detectie;
   - header;
   - totals;
   - articles;
   - filters;
   - diagnostics.
4. Na elke stap bestaande testset draaien.
5. Geen parsergedrag wijzigen tijdens pure verplaatsingsstappen.

## Acceptatiecriteria voor toekomstige wijzigingen

Elke wijziging in Receipt Ingestion moet aantonen:

- in welke laag de wijziging thuishoort;
- dat generieke bestanden geen nieuwe winkelregels krijgen;
- dat winkelregels alleen in profielen staan;
- dat `receipt_status_baseline_service_v4.py` eigenaar blijft van status;
- dat `total_amount` niet uit artikelregelsommen wordt afgeleid;
- dat diagnose/export geen productiegegevens muteert.
