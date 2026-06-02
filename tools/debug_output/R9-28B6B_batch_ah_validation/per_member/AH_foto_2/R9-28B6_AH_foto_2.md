# R9-28B6 — AH Paddle-box section and column reconstruction

Gemaakt: `2026-05-24T20:01:30`

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

- `paddle_item_count`: `69`
- `blocked_non_article_count`: `31`
- `reconstructed_article_count`: `2`
- `reconstructed_article_sum`: `8.28`

## Gereconstrueerde artikelregels

- `AH M GEHAKT` — `6,99` — rule `AH_PADDLE_BOX_DESCRIPTION_AMOUNT_PAIR_RULE`
- `SOEPGR BASIS` — `1,29` — rule `AH_PADDLE_BOX_DESCRIPTION_AMOUNT_PAIR_RULE`

## Geblokkeerde niet-artikelitems

- `Albert Heijn Ger Koopman` → `AH_HEADER`
- `PRIJS BEDRAG` → `AH_COLUMN_HEADER`
- `OMSCHRIJVING` → `AH_COLUMN_HEADER`
- `AANTAL` → `AH_COLUMN_HEADER`
- `SUBTOTAAL` → `AH_TOTAL_OR_SUBTOTAL`
- `JOUW VOORDEEL` → `AH_DISCOUNT`
- `waarvan` → `AH_DISCOUNT`
- `BONUS BOX` → `AH_DISCOUNT`
- `TOTAAL` → `AH_TOTAL_OR_SUBTOTAL`
- `BETAALD MET:` → `AH_PAYMENT`
- `PINNEN` → `AH_PAYMENT`
- `POI: 50100891` → `AH_PAYMENT`
- `Merchant` → `AH_PAYMENT`
- `Terminal` → `AH_PAYMENT`
- `Transactie` → `AH_PAYMENT`
- `Periode` → `AH_PAYMENT`
- `Token 1` → `AH_PAYMENT`
- `Kaart` → `AH_PAYMENT`
- `BETALING` → `AH_PAYMENT`
- `Kaartserienummer` → `AH_PAYMENT`
- `Autorisatiecode` → `AH_PAYMENT`
- `Contactless` → `AH_PAYMENT`
- `8,28 EUR` → `AH_TAX`
- `Totaal` → `AH_TOTAL_OR_SUBTOTAL`
- `Leesmethode CHIP` → `AH_PAYMENT`
- `EUR` → `AH_TAX`
- `OVER` → `AH_TAX`
- `BTW` → `AH_TAX`
- `9%` → `AH_TAX`
- `TOTAAL` → `AH_TOTAL_OR_SUBTOTAL`
- `Vragen over je kassabon?` → `AH_TAX`

## Kolomankers

```json
{
  "description_x": 404.5,
  "description_min_x": 228.0,
  "quantity_x": 179.5,
  "amount_min_x": 662.0
}
```

## Vervolg

Use this diagnostic result to validate AH chain rules across all AH receipts before touching runtime parser logic.
