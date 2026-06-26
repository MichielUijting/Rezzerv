# M2C2i-24S — Blind coverage-test voor nieuwe bonartikelen

## Doel

M2C2i-24S bewijst dat de herkenningsstraat niet afhankelijk is van vooraf bekende artikelnamen.

De scan neemt actuele bonartikelen dynamisch uit de bestaande Rezzerv-runtime en voert per regel dezelfde kandidaatdiagnose uit.

## Kernprincipe

Geen vooraf samengestelde artikellijst.

Wel:

1. actuele bonartikelen ophalen via de bestaande receipt-items flow;
2. per unieke bonartikelcontext de herkenningsstraat uitvoeren;
3. per regel rapporteren of er echte bronkandidaten bestaan;
4. ontbreken van brondata veilig rapporteren als geen echte bronmatch;
5. verboden fallback- of pseudo-artikelen expliciet tellen.

## Endpoint

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

## Uitkomst

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
