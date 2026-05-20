# R7c-16 — Perspective & Geometry Diagnostics

## Doel

R7c-16 onderzoekt diagnostic-only waarom AH foto 3 geometrisch verkeerd wordt geïnterpreteerd.

Belangrijk:

Deze stap wijzigt:

- geen productieparser;
- geen receipt_service gedrag;
- geen statuslogica;
- geen frontend;
- geen OCR-routing;
- geen productie-topology reconstruction.

## Probleemstelling

R7c-12 tot en met R7c-15 lieten zien:

- OCR werkt gedeeltelijk;
- semantic filtering werkt;
- region scoring werkt beter;
- maar topology reconstruction koppelt vooral footer/paymentregels.

Voorbeelden:

- "TOTAAL Leesmethode NFC Chip 5,40"
- "X1J9U8 Periode Terminal 5,40"
- "os Datum 5,40"

De hypothese is:

```text
perspectiefvervorming + niet-genormaliseerde geometry
```

waardoor:

- echte artikelregels uiteen vallen;
- prijskolommen verkeerd alignen;
- footerregels geometrisch stabieler lijken.

## Nieuwe diagnostische outputs

R7c-16 genereert:

- originele receipt-overlay;
- polygon detectie;
- perspective warp preview;
- OCR-box overlays;
- line clustering overlays;
- price pair overlays.

## Nieuwe analysepunten

### Receipt polygon

Analyse van:

- vierpuntscontour;
- trapeziumvervorming;
- convergentieratio;
- rotatiehoek.

### OCR box geometry

Analyse van:

- boxposities;
- lijnhoogtes;
- horizontale alignering;
- prijsboxen versus tekstboxen.

### Line clustering

Visualisatie van:

- welke OCR-boxes tot één regel worden gegroepeerd;
- waar regels uiteen vallen;
- welke regels foutief worden samengevoegd.

### Pair reconstruction

Visualisatie van:

- artikel-prijs koppelingen;
- footer/payment false positives;
- prijsanchors.

## Belangrijke architectuurregel

R7c-16 is:

```text
observability-first
```

Nog NIET:

- perspective-normalized production parsing;
- scoped topology reconstruction;
- article reconstruction.

Dat gebeurt pas nadat de geometrydiagnostiek bewezen heeft:

- waar de clustering breekt;
- of perspectiefnormalisatie echt noodzakelijk is.

## Verwachte vervolgstappen

Mogelijke vervolgrichtingen:

### R7c-17A

Perspective-normalized topology reconstruction.

### R7c-17B

Adaptive line clustering.

### R7c-17C

Price-column stabilization.

Welke route gekozen wordt hangt af van de overlays en geometry metrics van R7c-16.
