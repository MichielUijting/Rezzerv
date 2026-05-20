# R7c-14 — Receipt body region isolation diagnostics

## Doel

Diagnostic-only bepalen welke verticale regio van `AH foto 3.jpg` waarschijnlijk de echte artikel-body bevat.

## Aanleiding

R7c-12 en R7c-13 toonden:

- OCR leest store, datum en totaalbedrag correct;
- topology reconstruction vindt prijsankers;
- semantic filtering verwijdert payment/footer/totaal-noise correct;
- maar de echte artikelzone wordt nog niet geïsoleerd.

## Scope

Wel:

- alleen AH foto 3;
- raw PaddleOCR bounding boxes;
- verticale segmentatie;
- density scoring;
- semantic noise scoring;
- body-region candidate ranking.

Niet:

- geen parserwijziging;
- geen SSOT-wijziging;
- geen productiegedrag;
- geen OCR-route wijziging.

## Output per regio

```text
region_id
y_top
y_bottom
ocr_box_count
price_anchor_count
semantic_noise_count
article_candidate_density
body_region_score
```

## Besluitcriterium

Alleen als een regio duidelijk als waarschijnlijke artikel-body naar voren komt, mag een latere stap topology reconstruction beperken tot die regio.
