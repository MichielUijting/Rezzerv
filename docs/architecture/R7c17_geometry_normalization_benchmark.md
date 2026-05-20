# R7c-17 — Receipt Geometry Normalization Benchmark

## Doel

R7c-17 bepaalt diagnostic-only welke geometry/preprocessing-route de beste OCR-input oplevert voor AH foto 3.

Belangrijk:

Er wordt:

- geen productieparser aangepast;
- geen statuslogica aangepast;
- geen frontend aangepast;
- geen retailerlogica aangepast.

## Kerninzicht

R7c-16 liet zien:

- OCR zelf werkt redelijk;
- de receipt polygon detectie faalt;
- geometry-normalisatie waarschijnlijk de grootste bottleneck is.

De actuele Rezzerv-productieflow bewees bovendien dat:

```text
correcte rotatie + betere cropping
```

veel betere OCR-resultaten opleveren.

## Benchmark-routes

De tool vergelijkt minimaal:

1. original
2. rotate_only
3. rotate_crop
4. rotate_perspective
5. rotate_perspective_contrast

## Per route meten

### OCR metrics

- OCR-regelcount
- aantal price anchors
- article-like line count
- footer/payment line count
- parseability score

### Semantische voorbeelden

- sample article lines
- sample footer lines
- totaalbedragkandidaten

## Architectuurdoel

Het doel is niet:

```text
meer parserregels bouwen
```

maar:

```text
de OCR betere input geven
```

## Verwachte vervolgstap

Als een route duidelijk beter presteert:

R7c-18 — Integrate Best Geometry Normalization Route

waarbij de beste preprocessing-route wordt opgenomen vóór OCR.
