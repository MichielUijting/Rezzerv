# M2C2i-19S — Geen fallback, alleen echte kandidaten

## Doel

Onbekende bonregels mogen geen pseudo-kandidaat krijgen op basis van alleen de bonregeltekst.

```text
bonregel
-> echte externe/catalogusmatch?
-> kandidaat tonen

bonregel
-> geen echte externe/catalogusmatch?
-> geen kandidaat tonen
```

## Verwijderd principe

Deze kandidaattypes zijn functioneel verworpen:

```text
receipt_product_intent_fallback
receipt_unresolved_fallback
learned_receipt_line
concept_candidate
```

Reden: deze kandidaten geven de bonregel zelf terug als zogenaamd artikel. Dat levert ruis op en geen echte herkenning.

## Toegestaan

Alleen echte bronnen mogen kandidaten leveren:

```text
lidl_catalog_enrichment
external_product_index
OFF-index
product_taxonomy_seed, alleen als die naar echte brondata verwijst
```

## Gedrag

- Als de bestaande index of catalogus geen match heeft, blijft de kandidaatlijst leeg.
- `ensure_candidate_coverage` maakt geen fallback meer.
- De compatibility-wrapper `build_receipt_fallback_candidate` bestaat nog om imports niet te breken, maar retourneert alleen een echte cataloguskandidaat of `None`.
- Er wordt niets geschreven naar `external_product_index`.
- Er wordt geen `global_product`, Mijn artikel of voorraadmutatie aangemaakt.

## Safety

```text
creates_global_product = false
creates_household_article = false
creates_inventory_event = false
uses_coverage_fallback = false
uses_legacy_fallback = false
```

## Buiten scope

- Geen frontendwijziging.
- Geen self-learning.
- Geen JSON-uitbreiding.
- Geen conceptkandidaat.
- Geen resolved-state gate.
