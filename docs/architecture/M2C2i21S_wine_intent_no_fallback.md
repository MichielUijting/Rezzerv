# M2C2i-21S — Wijn-intent herkennen zonder fallback

## Doel

Rezzerv moet bonregel `Argentijnse Malbec` inhoudelijk kunnen duiden als wijn, zonder daar automatisch een kandidaatartikel van te maken.

```text
Argentijnse Malbec
-> product_intent = wijn
-> product_type = rode wijn
-> variant_terms bevat argentijnse en malbec
-> geen echte brondata?
-> geen kandidaat
```

## Uitgangspunt

M2C2i-21S bouwt voort op M2C2i-20S.

M2C2i-20S voegde diagnose toe. M2C2i-21S verbetert de analyse-laag zodat de diagnose beter uitlegt wat de bonregel betekent.

## Geen fallback

Deze stap maakt nog steeds geen pseudo-kandidaat.

Niet toegestaan:

```text
receipt_product_intent_fallback
receipt_unresolved_fallback
learned_receipt_line
concept_candidate
```

## Nieuwe data

Nieuwe intent-overrides staan los van `external_product_index`:

```text
backend/app/data/receipt_intent_overrides.json
```

Deze data is alleen bedoeld voor analyse, niet voor kandidaatgeneratie.

## Nieuwe analyse

Voor `Argentijnse Malbec` verwacht de diagnose:

```text
product_intent = wijn
category = wijn
product_type = rode wijn
variant_terms bevat argentijnse en malbec
real_candidate_count = 0 zolang echte brondata ontbreekt
```

## Safety

```text
writes_database = false
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
```

## Buiten scope

- Geen echte wijncatalogus toevoegen.
- Geen kandidaat maken voor Malbec.
- Geen self-learning.
- Geen fallback.
- Geen frontendwijziging.
- Geen voorraadmutatie.
