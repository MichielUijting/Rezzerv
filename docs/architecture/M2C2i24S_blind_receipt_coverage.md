# M2C2i-24S — Blind coverage-test voor nieuwe bonartikelen

## Doel

M2C2i-24S bewijst dat de herkenningsstraat niet afhankelijk is van vooraf bekende artikelnamen.

De scan neemt actuele bonartikelen dynamisch uit de bestaande Rezzerv-runtime en voert per regel dezelfde kandidaatdiagnose uit.

M2C2i-24S-a maakt dit daarnaast productgedrag: bij het opslaan van nieuwe bonartikelen wordt de externe kandidaatdekking automatisch aangeroepen.

## Kernprincipe

Geen vooraf samengestelde artikellijst.

Wel:

1. actuele bonartikelen ophalen via de bestaande receipt-items flow;
2. per unieke bonartikelcontext de herkenningsstraat uitvoeren;
3. per regel rapporteren of er echte bronkandidaten bestaan;
4. ontbreken van brondata veilig rapporteren als geen echte bronmatch;
5. verboden fallback- of pseudo-artikelen expliciet tellen.

Voor productgedrag:

1. een nieuwe bon wordt opgeslagen;
2. de bonregels worden uit `receipt_table_lines` opgehaald;
3. per bonregel wordt `ensure_external_receipt_item_candidates` aangeroepen;
4. echte kandidaten worden in `external_product_candidates` opgeslagen als kandidaatcache;
5. ontbrekende brondata blijft veilig zonder kandidaat.

## Endpoint voor PO-rapport

```text
POST /api/external-databases/coverage/receipt-items
```

Payload:

```json
{
  "limit": 500,
  "include_below_threshold": true
}
```

## Automatische hook

Nieuwe service:

```text
backend/app/services/external_receipt_auto_coverage.py
```

Belangrijkste functies:

```text
auto_ensure_external_candidates_for_receipt_table(receipt_table_id)
install_receipt_auto_candidate_coverage()
```

De startup-route installeert runtime hooks op:

```text
app.services.receipt_service.ingest_receipt
app.services.receipt_service.reparse_receipt
app.main.ingest_receipt
app.main.reparse_receipt
```

Daardoor krijgen gewone uploads en heranalyses automatisch kandidaatdekking na het opslaan van de bonregels.

## Uitkomst PO-rapport

Het endpoint retourneert een PO-rapport met samenvatting en detailregels:

```text
total_items
items_with_real_candidate
items_without_real_candidate
items_with_forbidden_fallback
candidate_count
real_candidate_count
forbidden_candidate_count
coverage_fallback_item_count
legacy_fallback_item_count
```

Per bonartikel:

```text
receipt_line_text
retailer_code
candidate_count
real_candidate_count
forbidden_candidate_count
has_real_candidate
candidate_source
no_candidate_reason
best_candidate.candidate_name
best_candidate.candidate_source_name
best_candidate.candidate_source_product_code
```

## Uitkomst automatische hook

De ingest-response krijgt bij een nieuwe, niet-dubbele bon:

```text
external_candidate_coverage.ok
external_candidate_coverage.receipt_table_id
external_candidate_coverage.item_count
external_candidate_coverage.processed
external_candidate_coverage.saved_count
external_candidate_coverage.updated_count
external_candidate_coverage.skipped_count
```

## Veiligheidsregels

M2C2i-24S maakt geen:

- Mijn artikel;
- global product;
- product identity;
- voorraadmutatie;
- fallback-kandidaat;
- concept candidate;
- learned receipt line.

Het rapport zet daarom expliciet:

```text
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
writes_database = false
```

De automatische hook schrijft wel kandidaatcache in `external_product_candidates`, maar blijft binnen dezelfde grenzen:

```text
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
```

## Interpretatie

Een bonartikel hoeft niet altijd een kandidaat te krijgen.

Correct gedrag is:

```text
brondata aanwezig  → echte kandidaat
brondata ontbreekt → geen echte bronmatch
```

Fout gedrag is:

```text
brondata ontbreekt → fallback-artikel / pseudo-artikel / learned_receipt_line
```
