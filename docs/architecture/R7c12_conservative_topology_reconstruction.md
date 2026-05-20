# R7c-12 — Conservative topology reconstruction diagnostics

## Doel

Diagnostic-only onderzoeken of `AH foto 3.jpg` beter geïnterpreteerd kan worden via regel- en kolomtopologie op basis van de bestaande beste OCR-route:

```text
raw_paddle_current
```

## Aanleiding

R7c-11d toonde dat `raw_paddle_current` voor AH foto 3 de beste route is:

- store_name wordt herkend;
- purchase_at wordt herkend;
- total_amount wordt herkend;
- article_line_count blijft 0.

De bottleneck ligt daarom niet primair in OCR-preprocessing, maar in topology reconstruction.

## Scope

Wel:

- alleen AH foto 3;
- diagnostic-only;
- Paddle bounding boxes gebruiken;
- prijsankers detecteren;
- kandidaat artikel-prijs paren rapporteren;
- verklaren waarom artikelregels nu niet ontstaan.

Niet:

- geen parserwijziging;
- geen SSOT-wijziging;
- geen productie-routing;
- geen unwarping/perspective correction;
- geen AH-specifieke parserhack.

## Diagnostische output

De runner rapporteert minimaal:

```text
fixture_file
ocr_box_count
raw_ocr_line_count
topology_line_count
price_anchor_count
candidate_article_price_pairs
reconstructed_article_line_count
detected_total_amount
store_name
purchase_at
diagnostic_only
```

## Besluitcriterium

Alleen als R7c-12 laat zien dat artikelregels betrouwbaar kunnen worden gereconstrueerd, mag een latere stap een gecontroleerde image-topology fallback voorbereiden.
