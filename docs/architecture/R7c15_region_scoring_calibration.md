# R7c-15 — Region Scoring Calibration

## Doel

R7c-15 corrigeert de diagnostic-only body-region scoring voor AH foto 3.

R7c-14 liet een belangrijke fout zien:

- een footer/payment-regio zonder prijsanchors kon alsnog winnen;
- een regio met alleen lage semantic noise werd te positief gewaardeerd;
- positieve article-body signalen kregen onvoldoende gewicht.

Belangrijk:

Deze stap blijft volledig diagnostic-only.

Er wordt:

- geen productieparser aangepast;
- geen receipt_service gedrag gewijzigd;
- geen statuslogica aangepast;
- geen productie-routing aangepast.

## Probleem in R7c-14

R7c-14 gebruikte een eenvoudige score:

- article_candidate_density
- price_anchor_count
- ocr_box_count
- semantic_noise_count

Daardoor kon:

- een regio zonder article evidence;
- zonder prijsanchors;
- maar met weinig noise;

nog steeds de hoogste body-region score krijgen.

Bij AH foto 3 gebeurde precies dat:

- region_4 (onderste footer/payment-regio)
won de ranking.

## Nieuwe kalibratieregels

R7c-15 introduceert expliciete positieve en negatieve signalen.

### Positieve signalen

- price_anchor_count
- article_candidate_density
- article_candidate_count
- pair_alignment_count
- ocr_presence_score

### Negatieve signalen

- semantic_noise_count
- footer_keyword_hit_count
- missing_price_anchor_penalty

## Harde beslisregel

Nieuwe regel:

```text
Een regio zonder price anchors mag niet winnen
wanneer een andere regio wel price anchors bevat.
```

Daarom krijgt een anchor-loze regio:

- een harde penalty;
- en wordt zij gemarkeerd als:

```text
eligible_body_region = false
```

zodra andere regio’s wel anchors bevatten.

## Nieuwe scorestructuur

Conceptueel:

```text
score =
  + price_anchor_score
  + article_density_score
  + article_candidate_score
  + pair_alignment_score
  + ocr_presence_score
  - semantic_noise_penalty
  - footer_keyword_penalty
  - no_price_anchor_penalty
```

## Belangrijk architectuurprincipe

R7c-15 kalibreert alleen de ranking.

Nog NIET:

- topology reconstruction scopen;
- parser aanpassen;
- OCR vervangen;
- productiegedrag wijzigen.

Dat voorkomt regressies.

## Verwachte vervolgstap

Pas na succesvolle scoring calibration:

R7c-16 — Scoped Topology Reconstruction

waarbij topology reconstruction alleen draait binnen:

```text
best_region
```

zoals bepaald door de gekalibreerde ranking.
