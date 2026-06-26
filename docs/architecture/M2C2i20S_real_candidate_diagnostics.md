# M2C2i-20S — Diagnose echte kandidaatdekking

## Doel

M2C2i-20S verklaart waarom een bonregel wel of geen echte kandidaat krijgt.

```text
bonregel
-> echte bronnen raadplegen
-> geen fallback maken
-> diagnose teruggeven
```

## Uitgangspunt

M2C2i-20S bouwt voort op M2C2i-19S.

M2C2i-19S verwijderde fallback-kandidaten. M2C2i-20S voegt alleen diagnose toe, zodat we gericht kunnen bepalen welke echte bron ontbreekt of waarom matching faalt.

## Nieuwe service

```text
backend/app/services/external_candidate_diagnostics.py
```

Deze service geeft onder meer terug:

```text
candidate_count
real_candidate_count
forbidden_candidate_count
has_real_candidate
has_forbidden_fallback_candidate
diagnostic_reasons
index_probe
saved_candidate_probe
receipt_analysis
```

## Nieuwe API-route

```text
POST /api/external-databases/retailers/{retailer_code}/diagnose-real-candidates
```

Body:

```json
{
  "receipt_line_text": "voorbeeld bonregel",
  "include_below_threshold": true
}
```

## Safety

De diagnose schrijft niets.

```text
writes_database = false
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
```

## Buiten scope

- Geen frontendwijziging.
- Geen fallback.
- Geen self-learning.
- Geen JSON-uitbreiding.
- Geen kandidaatbevestiging.
- Geen voorraadmutatie.
