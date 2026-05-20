# R7c-8 — Paddle OCR text-layout diagnostics

## Doel

Diagnostisch onderzoeken of OCR text-layout clustering meerdere receipt-regio’s beter detecteert dan contour-first analyse.

## Belangrijke ontwerpregel

R7c-8 is:

```text
diagnostic_only = true
```

Dus:

- geen parserwijziging;
- geen SSOT-wijziging;
- geen crop-integratie;
- geen supermarkt-specifieke heuristiek.

## Nieuwe boundary

Toegevoegd:

```text
backend/app/receipt_ingestion/text_layout_regions.py
```

Deze boundary bevat:

- OCR bounding-box parsing;
- text region clustering;
- region scoring;
- multi-text-region diagnostics.

## Runner

Toegevoegd:

```text
tools/check_r7c8_paddle_text_layout_diagnostics.py
```

## Kernidee

Niet zoeken naar papiercontouren, maar naar:

- verticale tekststructuren;
- line clustering;
- text-density groepen.

## Verwachting

Voor `Plus foto 2.jpeg` moet zichtbaar worden:

```text
multi_text_regions_detected = true
```

zonder parsergedrag te wijzigen.
