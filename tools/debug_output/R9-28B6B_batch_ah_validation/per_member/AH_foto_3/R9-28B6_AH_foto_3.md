# R9-28B6 — AH Paddle-box section and column reconstruction

Gemaakt: `2026-05-24T20:01:56`

## SSOT-compliance

- `status_determination`: `not_performed`
- `status_service`: `receipt_status_baseline_service_v4.py`
- `parse_status_used_as_truth`: `False`
- `parser_mutated`: `False`
- `ocr_mutated`: `False`
- `database_mutated`: `False`
- `baseline_mutated`: `False`
- `ui_touched`: `False`
- `diagnostics_promoted_to_parser`: `False`

## Samenvatting

- `paddle_item_count`: `70`
- `blocked_non_article_count`: `37`
- `reconstructed_article_count`: `2`
- `reconstructed_article_sum`: `5.4`

## Gereconstrueerde artikelregels

- `CHAUDF WATER` — `5,40` — rule `AH_PADDLE_BOX_DESCRIPTION_AMOUNT_PAIR_RULE`
- `AH SANDWICH` — `0,00` — rule `AH_PADDLE_BOX_DESCRIPTION_AMOUNT_PAIR_RULE`

## Geblokkeerde niet-artikelitems

- `Albert Heijn` → `AH_HEADER`
- `Albert Heiin to go` → `AH_HEADER`
- `Station Groningen` → `AH_HEADER`
- `Telefoon 050-3135315` → `AH_HEADER`
- `BEDRAG` → `AH_COLUMN_HEADER`
- `PRIJS` → `AH_COLUMN_HEADER`
- `OMSCHRIJVING` → `AH_COLUMN_HEADER`
- `AANTAL` → `AH_COLUMN_HEADER`
- `SUBTOTAAL` → `AH_TOTAL_OR_SUBTOTAL`
- `VOORDEEL` → `AH_DISCOUNT`
- `waarvan` → `AH_DISCOUNT`
- `App Deals` → `AH_DISCOUNT`
- `TE BETALEN` → `AH_TOTAL_OR_SUBTOTAL`
- `BETAALD MET:` → `AH_PAYMENT`
- `PINNEN` → `AH_PAYMENT`
- `Terminal` → `AH_PAYMENT`
- `POI: 50047284` → `AH_PAYMENT`
- `Periode` → `AH_PAYMENT`
- `VPAY` → `AH_PAYMENT`
- `Merchant` → `AH_PAYMENT`
- `V-PAY` → `AH_PAYMENT`
- `Kaartserienummer` → `AH_PAYMENT`
- `Transactie` → `AH_PAYMENT`
- `5,40 EUR` → `AH_TAX`
- `Kaart xxxxxxxxxxxxxxx5103` → `AH_PAYMENT`
- `Totaal` → `AH_TOTAL_OR_SUBTOTAL`
- `BETALING` → `AH_PAYMENT`
- `Autorisatiecode` → `AH_PAYMENT`
- `EUR` → `AH_TAX`
- `Leesmethode NFC Chip` → `AH_PAYMENT`
- `OVER` → `AH_TAX`
- `BTW` → `AH_TAX`
- `9%` → `AH_TAX`
- `TOTAAL` → `AH_TOTAL_OR_SUBTOTAL`
- `Download nu de AH to go app!` → `AH_FOOTER`
- `Spaar automatisch en krijg` → `AH_FOOTER`
- `gratis een product.` → `AH_FOOTER`

## Kolomankers

```json
{
  "amount_x": 1142.0,
  "amount_min_x": 969.0,
  "price_x": 950.0,
  "description_x": 668.5,
  "description_min_x": 460.0,
  "quantity_x": 356.0
}
```

## Vervolg

Use this diagnostic result to validate AH chain rules across all AH receipts before touching runtime parser logic.
