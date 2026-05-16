# Fase 8I-0 — Parser code-path inventory

Status: uitgevoerd als code-inventarisatie, zonder parserwijziging.

## Doel

Bepalen waar artikelregelfixes veilig moeten inhaken voordat Fase 8I-1/8I-2 wordt gebouwd.

## Scope gelezen codepad

### 1. Invoer en OCR

`parse_receipt_content(...)` kiest per bestandstype het pad:

- PDF: directe PDF-tekst, daarna OCR fallback.
- Afbeelding: PaddleOCR en Tesseract, waarna het beste parse-resultaat wordt gekozen.
- E-mail/HTML/TXT: tekstextractie en store-specific parsers.

De centrale output is steeds `ReceiptParseResult` met `lines`, `total_amount`, `discount_total`, `purchase_at`, `store_name` en `parse_status`.

### 2. Centrale artikelregelproductie

De generieke artikelregels ontstaan in:

```text
_parse_result_from_text_lines(...)
  -> _extract_receipt_lines(...)
  -> _extract_savings_action_lines(...)
  -> _filter_non_product_receipt_lines(...)
  -> _apply_discount_entries(...)
  -> _filter_non_product_receipt_lines(...)
  -> _totals_match_receipt_lines(...)
```

Belangrijk: dit is de juiste centrale plek voor artikelkwaliteit. Status hoort hier niet te worden geforceerd.

### 3. Huidige filters

Er bestaan al generieke en ALDI-specifieke filters:

- `_should_skip_receipt_line(...)`
- `_looks_like_non_product_receipt_label(...)`
- `_looks_like_aldi_vat_summary_line(...)`
- `_looks_like_aldi_payment_line(...)`
- `_is_invalid_aldi_article_candidate(...)`
- `_filter_non_product_receipt_lines(...)`

Deze laag is de veiligste plek voor Fase 8I-1: false article filters.

### 4. Huidige extractieregels

`_extract_receipt_lines(...)` gebruikt drie hoofdpatronen:

- `qty_first_re`
- `label_first_re`
- `detail_only_re`

Daarnaast is er `pending_label`/`pending_line_index`-logica om detailregels te koppelen aan de vorige artikelregel.

Deze laag is de juiste plek voor:

- Lidl gewichtregel koppelen aan vorig artikel.
- `N x prijs` normaliseren.
- Voorloopaantallen verwerken.

### 5. Huidige korting-/zegelverwerking

Korting en acties zitten in:

- `_extract_discount_entries(...)`
- `_apply_discount_entries(...)`
- `_extract_savings_action_lines(...)`

Deze laag moet pas na false article filtering worden aangepast, omdat foute artikelregels nu de kortingmatching kunnen vervuilen.

### 6. Diagnosepad

`/api/testing/receipt-line-diagnosis` gebruikt:

- opgeslagen `receipt_table_lines`;
- live reparse via `parse_receipt_content(...)`;
- baseline via `receipt_status_baseline_service_v4.py`.

Het endpoint is read-only en geschikt als regressiemeetpunt na elke subfase.

## Conclusies uit code-inspectie

### A. Fase 8I-1 moet starten met filters, niet met totalen

De line-diagnose toont foutieve artikelregels zoals openingstijden, BTW-regels, totalen, zegels en numerieke regels. De code heeft al een filterlaag; die moet worden aangescherpt voordat regelsommen of totaalvalidatie worden aangepast.

### B. Retailer-specifieke fixes horen deels in bestaande generieke service

Er is geen actieve aparte profile-laag in het runtimepad van deze backend. De effectieve productieparser zit nu in `backend/app/services/receipt_service.py`. Fixes moeten daarom daar worden aangebracht, bij voorkeur via kleine helperfuncties per winkel binnen de bestaande flow.

### C. Status blijft buiten scope

`parse_status` wordt afgeleid uit parsekwaliteit, maar PO-status komt via de baseline/SSOT. Fase 8I mag geen status forceren.

### D. De hardcoded Jumbo-fallback is risicovol

Er staat een specifieke fallback voor `jumbo foto 3.jpg` die een nulbedragregel `Jumbo stroopwafels` kan creëren. Dit verklaart waarom deze bon gecontroleerd kan lijken terwijl totaal en regel nul zijn. Dit hoort in een latere cleanupfase, niet in 8I-1 false article filtering.

## Aanbevolen volgorde na 8I-0

### Fase 8I-1 — ALDI + PLUS false article filters

Doel:

- ALDI: openingstijden (`ZON 10.00`, `ZA 8.00`, `ZO 12.00`) en BTW-regels (`B 9,00% ...`) weren.
- PLUS: losse totaalregels, zegelregels en numerieke ruis (`50.89`, `26 11:01 ... zegels`) weren.
- Jumbo: actieperiode/weekdagregels zoals `Maandag t/m Woensdag` weren.

Inhaakpunt:

```text
_should_skip_receipt_line(...)
_looks_like_non_product_receipt_label(...)
_filter_non_product_receipt_lines(...)
```

Acceptatie:

- false article count daalt;
- geen statuswijziging forceren;
- `receipt-line-diagnosis` laat minder ruisregels zien;
- reeds gecontroleerde bonnen blijven stabiel.

### Fase 8I-2 — Lidl weight-line merge

Doel:

- regels zoals `1,224 kg x` koppelen aan vorig artikel in plaats van als los artikel opslaan.

Inhaakpunt:

```text
_extract_receipt_lines(...)
pending_line_index / detail_only_re
```

### Fase 8I-3 — Quantity normalization

Doel:

- voorloopaantallen en `N x prijs` consequent in `quantity` zetten zonder artikelnaam te vervuilen.

Inhaakpunt:

```text
append_line(...)
qty_first_re
label_first_re
```

### Fase 8I-4 — PLUS split/merge

Doel:

- geplakte PLUS-productregels splitsen zodra filters en quantity-merge stabiel zijn.

## Testprotocol na elke subfase

1. `git pull`
2. patchscript uitvoeren
3. `docker compose up -d --build`
4. 14 bonnen opnieuw importeren
5. `GET /api/testing/receipt-line-diagnosis/download`
6. `GET /api/receipt-kpi/baseline`

## Niet doen in 8I

- Geen wijziging aan `receipt_status_baseline_service_v4.py`.
- Geen UI-wijziging.
- Geen DB-migratie.
- Geen totaalvalidatie versoepelen.
- Geen status forceren naar Gecontroleerd.
