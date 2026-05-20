# R7c-11 — Image preprocessing route diagnostics

## Doel

Diagnostic-only vergelijking van meerdere OCR-routes voor scheve/vervormde supermarkt-kassabonnen.

Specifieke focus:
- AH foto 3.jpg
- geometrische OCR-instabiliteit
- perspectief-/layoutfragmentatie

## Buiten scope

Niet toegestaan:
- productieparser wijzigen;
- SSOT wijzigen;
- receipt statuslogica wijzigen;
- winkel-specifieke heuristieken;
- database writes.

## Geteste routes

- raw_paddle_current
- paddle_orientation_enabled
- paddle_unwarping_enabled
- tesseract_psm6_current
- tesseract_psm4
- tesseract_psm11

## Doel van de vergelijking

Vaststellen welke OCR-route:
- stabiel totaalbedrag oplevert;
- voldoende artikelregels behoudt;
- store_name correct houdt;
- geometrische fragmentatie minimaliseert.

## Verwachte architectuuruitkomst

Mogelijke vervolgstappen:

1. extra OCR-candidate route toevoegen;
2. preprocessing-route toevoegen;
3. topology grouping verbeteren;
4. OpenCV deskew/perspective diagnostics toevoegen.

## Belangrijk

Deze stap is volledig diagnostic-only.
Geen productiegedrag mag wijzigen.
